import re
from dataclasses import dataclass

import discord
from discord.ext import commands

import breadcord
from breadcord.helpers import simple_button


@dataclass
class Meaning:
    word_class: str | None
    definition: str
    example: str | None
    synonyms: list[str]
    antonyms: list[str]


@dataclass
class Word:
    word: str
    phonetic_str: str | None
    phonetic_audio_url: str | None
    meanings: list[Meaning]


class AuthorDeleteView(discord.ui.View):
    def __init__(self, author_id: int | None = None):
        super().__init__(timeout=None)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None:
            return await super().interaction_check(interaction)
        return interaction.user.id == self.author_id

    @simple_button(label="Delete", style=discord.ButtonStyle.red, emoji="🗑️")
    async def delete(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        await interaction.message.delete()


def clean_for_url(word: str) -> str:
    return "".join(filter(lambda x: x.isalnum() or x.isspace(), word.lower().strip()))


def most_comprehensive(words: list[Word]) -> Word:
    return max(words, key=lambda x: len(x.word))


class Definitions(breadcord.helpers.HTTPModuleCog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot.add_view(AuthorDeleteView())

    async def get_dictionary_def(self, word: str) -> list[Word] | None:
        word = clean_for_url(word)
        async with self.session.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}") as response:
            if not response.ok:
                return
            if not (data := await response.json()):
                return

        words: list[Word] = []
        for word_data in data:
            phonetic_str = phonetic_audio_url = None
            if phonetics := word_data.get("phonetics"):
                phonetics = sorted(
                    phonetics,
                    key=lambda x: (bool(x.get("text")) * 2) + bool(x.get("audio") * 1),
                    reverse=True,
                )
                phonetic_str = phonetics[0].get("text")
                phonetic_audio_url = phonetics[0].get("audio")

            meanings = []
            # Should KeyError if there's no meanings, otherwise this function is meaningless!
            for meaning in word_data["meanings"]:
                for definition in meaning["definitions"]:
                    meanings.append(Meaning(
                        word_class=meaning.get("partOfSpeech"),
                        definition=definition["definition"],
                        example=definition.get("example") or None,
                        synonyms=definition.get("synonyms") or [],
                        antonyms=definition.get("antonyms") or [],
                    ))

            words.append(Word(
                word=word_data["word"],
                phonetic_str=phonetic_str,
                phonetic_audio_url=phonetic_audio_url,
                meanings=meanings,
            ))
        return words or None

    async def get_urban_dictionary_def(self, word: str) -> list[Word] | None:
        word = clean_for_url(word)
        async with self.session.get(f"https://api.urbandictionary.com/v0/define?term={word}") as response:
            if not response.ok:
                return
            if not (data := await response.json()):
                return
            if not (data := data.get("list")):
                return

        def cleanup_ud_def(text: str) -> str:
            # Some words will have square brackets surrounding them, I think they're meant to be hyperlinks on the site
            return re.sub(r"\[(.*?)]", r"\1", text)

        meanings = [
            Meaning(
                word_class=None,
                definition=cleanup_ud_def(word_data["definition"]),
                example=cleanup_ud_def(word_data.get("example") or "") or None,
                synonyms=[],
                antonyms=[]
            )
            for word_data in data
            if word_data["word"].lower() == word.lower()
        ]
        return [Word(
            word=data[0]["word"],
            meanings=meanings,
            phonetic_str=None,
            phonetic_audio_url=None,
        )] if meanings else None

    @staticmethod
    def build_word_embed(word: Word) -> discord.Embed:
        embed = discord.Embed(
            title=word.word,
            description=(
                f"[`{word.phonetic_str}`]({word.phonetic_audio_url})"
                if word.phonetic_audio_url else
                f"`{word.phonetic_str}`"
            ) if word.phonetic_str else None,
            color=discord.Color.blurple(),
        )

        average_length = sum(len(meaning.definition + (meaning.example or "")) for meaning in word.meanings)
        average_length //= len(word.meanings)
        number = max(1, min(6, round(
            -average_length / 60 + 7
        )))
        for i, meaning in enumerate(word.meanings[:number]):
            embed.add_field(
                name=meaning.word_class or f"Meaning {i + 1}",
                value="\n".join(line for line in (
                    f"**Definition:** {meaning.definition}",
                    f"**Example:** {meaning.example}" if meaning.example else None,
                    f"**Synonyms:** {', '.join(meaning.synonyms)}" if meaning.synonyms else None,
                    f"**Antonyms:** {', '.join(meaning.antonyms)}" if meaning.antonyms else None,
                ) if line),
                inline=False,
            )

        return embed

    async def normal_embed(self, word: str) -> discord.Embed | None:
        words = await self.get_dictionary_def(word)
        if not words:
            return None

        embed = self.build_word_embed(most_comprehensive(words))
        embed.set_footer(text="Definitions sourced from Dictionary API")
        return embed

    async def urban_dictionary_embed(self, word: str) -> discord.Embed | None:
        words = await self.get_urban_dictionary_def(word)
        if not words:
            return None

        embed = self.build_word_embed(most_comprehensive(words))
        embed.colour = 0xEFFF00
        embed.set_footer(text="Definitions sourced from Urban Dictionary")
        return embed

    @commands.hybrid_command()
    async def define(self, ctx: commands.Context, *, query: str, urban: bool = False):
        if not query:
            return await ctx.reply("You need to provide a word to define")

        deletable = False
        embed = None
        if not urban:
            embed = await self.normal_embed(query)
        if urban or not embed:
            embed = await self.urban_dictionary_embed(query)
            deletable = True
        if urban and not embed:
            embed = await self.normal_embed(query)
        if not embed:
            return await ctx.reply("No definitions found for that word")

        await ctx.reply(
            embed=embed,
            view=AuthorDeleteView(ctx.author.id) if deletable else None,
        )


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Definitions("breadcord_definitions"))
