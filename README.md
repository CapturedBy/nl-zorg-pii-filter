# nl-zorg-pii-filter

[![CI](https://github.com/CapturedBy/nl-zorg-pii-filter/actions/workflows/ci.yml/badge.svg)](https://github.com/CapturedBy/nl-zorg-pii-filter/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Mask Dutch personal data **before** text goes to a language model, and put it back **after**.
Zero dependencies, rule-based, built for healthcare text (triage calls, intake notes, patient
messages) where a BSN or a name must never leave the practice.

```
Goedemorgen, u spreekt met Anna de Groot. Ik bel voor mijn vader, dhr. J. de Groot,
geboren 14-03-1951, BSN 100000708. Hij woont op Oosterkade 14, 9711 RS Groningen.
Sinds vannacht heeft hij pijn op de borst die uitstraalt naar zijn linkerarm en hij zweet.
U kunt mij terugbellen op 06-12345678 of mailen naar anna.degroot@example.nl.
```
becomes
```
Goedemorgen, u spreekt met [NAAM_1]. Ik bel voor mijn vader, dhr. [NAAM_2],
geboren [GEBOORTEDATUM_1], BSN [BSN_1]. Hij woont op [ADRES_1], [POSTCODE_1] Groningen.
Sinds vannacht heeft hij pijn op de borst die uitstraalt naar zijn linkerarm en hij zweet.
U kunt mij terugbellen op [TELEFOON_1] of mailen naar [EMAIL_1].
```
The clinical content is untouched; the model can still summarise, triage-structure or answer.
The mapping `[NAAM_1] → Anna de Groot` stays on your side, and `restore()` puts the real values
back into the model's reply.

## Why

The AVG (GDPR) and the NEN 7510 family expect data minimisation: send a processor only what it
needs. A triage assistant needs the complaint, not the BSN. This package makes that the default
in one line, instead of a prompt instruction the model may or may not follow.

## Install

```bash
pip install nl-zorg-pii-filter          # once published; until then:
pip install git+https://github.com/CapturedBy/nl-zorg-pii-filter
```

## Use

```python
from nl_zorg_pii import PiiFilter

f = PiiFilter()
masked = f.mask(transcript)        # masked.text is safe to send
reply = my_llm(masked.text)        # model sees [NAAM_1], [BSN_1], ...
answer = PiiFilter.restore(reply, masked.mapping)
```

`masked.counts()` tells you what was found (`{'BSN': 1, 'NAAM': 2, ...}`), `masked.matches` gives
positions, and `f.redact(text)` is the one-way version for logs.

Command line:

```bash
nl-pii check  notitie.txt                    # exit 1 if anything personal is in there (CI-friendly)
nl-pii mask   notitie.txt --mapping map.json > veilig.txt
nl-pii restore antwoord.txt --mapping map.json
```

## What it detects

| Kind | How | Notes |
|---|---|---|
| `BSN` | 8–9 digits passing the **elfproef** (11-check), with or without separators | Random 9-digit numbers that fail the check are left alone, so dossier numbers survive |
| `EMAIL` | standard pattern | |
| `TELEFOON` | Dutch numbers: `06-…`, `050 123 4567`, `+31 6 …` | Blood pressure `120/80` and `38.5` are not phone numbers |
| `IBAN` | `NL` + check digits + bank code | |
| `ADRES` | street suffix (`straat`, `laan`, `weg`, `kade`, …) + house number | |
| `POSTCODE` | `9711 RS` | |
| `GEBOORTEDATUM` | a full date preceded by *geboren*, *geboortedatum*, *geb.* | Consultation dates stay; `all_dates=True` masks every date |
| `NAAM` | title/role cue (*dhr.*, *mevrouw*, *patiënt*), introduction cue (*u spreekt met*, *ik ben*), or a known first name + surname | Built-in list of ~300 common Dutch first names; add your own with `extra_names=[...]` |

The same value always gets the same placeholder within a text, so `[NAAM_1]` means the same
person everywhere, and the model can refer to it consistently.

## What it does not do

- It is rule-based, not a model. It will miss unusual names without a cue and can over-match a
  capitalised word that happens to be a first name (*Mei*, *Max*). Use `kinds=` or
  `extra_names=` to tune it, and treat `nl-pii check` as a safety net, not a guarantee.
- It does not detect diagnoses, medication or other health information: that is the content the
  model is supposed to work on. Combine with a verwerkersovereenkomst and EU processing.
- Dates: only birth dates by default, on purpose.

## Extend

Any callable `text -> Iterator[Match]` is a detector:

```python
from nl_zorg_pii import PiiFilter, Match, default_detectors
import re

def detect_patient_id(text):
    for m in re.finditer(r"\bP-\d{6}\b", text):
        yield Match("PATIENTNR", m.start(), m.end(), m.group())

f = PiiFilter(detectors=[detect_patient_id, *default_detectors()])
```

(Add the new kind to the placeholder pattern in `filter.py` if you want `restore()` to handle it.)

## Development

```bash
pip install -e ".[dev]"
pytest --cov=nl_zorg_pii      # 29 tests, 99% coverage
ruff check . && ruff format --check .
python examples/llm_roundtrip.py   # add ANTHROPIC_API_KEY to see the full round trip
```

## Related

- [chatbot-eval-kit](https://github.com/CapturedBy/chatbot-eval-kit): regression-test the chatbot
  that receives the masked text.

## License

MIT © Marloes Gerdes
