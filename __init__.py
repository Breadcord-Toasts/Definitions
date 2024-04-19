import re
from dataclasses import dataclass

import discord
from discord.ext import commands

import breadcord


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


class Definitions(breadcord.helpers.HTTPModuleCog):
    async def get_dictionary_def(self, word: str) -> list[Word] | None:
        word = "".join(filter(lambda x: x.isalnum() or x.isspace(), word.lower().strip()))
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
        word = "".join(filter(lambda x: x.isalnum() or x.isspace(), word.lower().strip()))
        async with self.session.get(f"https://api.urbandictionary.com/v0/define?term={word}") as response:
            if not response.ok:
                return
            if not (data := await response.json()):
                return
            if not (data := data.get("list")):
                return

        def cleanup_ud_def(text: str) -> str:
            # Some words will have square brackets surrounding them
            return re.sub(
                r"\[(.*?)]",
                r"\1",
                text,
            )

        words: list[Word] = []
        for word_data in data:
            words.append(Word(
                word=word_data["word"],
                phonetic_str=None,
                phonetic_audio_url=None,
                meanings=[Meaning(
                    word_class=None,
                    definition=cleanup_ud_def(word_data["definition"]),
                    example=cleanup_ud_def(word_data.get("example") or "") or None,
                    synonyms=[],
                    antonyms=[],
                )],
            ))
        return words or None

    @staticmethod
    def build_word_embed(word: Word) -> discord.Embed:
        embed = discord.Embed(
            title=word.word,
            description=word.phonetic_str,
            color=discord.Color.blurple(),
        )

        for meaning in word.meanings[:6]:
            embed.add_field(
                name=f"{meaning.word_class or 'Unknown'}",
                value="\n".join(line for line in (
                    f"**Definition:** {meaning.definition}",
                    f"**Example:** {meaning.example}" if meaning.example else None,
                    f"**Synonyms:** {', '.join(meaning.synonyms)}" if meaning.synonyms else None,
                    f"**Antonyms:** {', '.join(meaning.antonyms)}" if meaning.antonyms else None,
                ) if line),
                inline=False,
            )

        return embed

    @commands.hybrid_command()
    async def define(self, ctx: commands.Context, *, query: str):
        words = await self.get_dictionary_def(query)
        if not words:
            words = await self.get_urban_dictionary_def(query)
        if not words:
            return await ctx.send("No definitions found for that word")

        await ctx.send(embed=self.build_word_embed(words[0]))


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Definitions("breadcord_definitions"))
