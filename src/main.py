import os
from google import genai

API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

prompt = """
Ti si scenarist za YouTube Shorts kanal.

Tema kanala:
robotika, umjetna inteligencija i tehnologija.

Napravi jedan potpuno novi YouTube Short na bosanskom jeziku.

Video treba trajati približno 45-60 sekundi.

Vrati TAČNO ovaj format:

TITLE:
[kratak zanimljiv naslov]

HOOK:
[prve 1-2 rečenice koje privlače pažnju]

SCRIPT:
[kompletna naracija za video]

DESCRIPTION:
[kratak opis videa]

TAGS:
[tag1, tag2, tag3, tag4, tag5]

Pravila:
- koristi jednostavan i prirodan bosanski jezik
- nemoj izmišljati činjenice
- nemoj ponavljati poznate klišee
- nemoj koristiti clickbait koji nije povezan sa sadržajem
- scenarij mora biti zanimljiv za gledanje do kraja
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

print(response.text)
