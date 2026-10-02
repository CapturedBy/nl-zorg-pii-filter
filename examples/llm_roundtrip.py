"""Mask → LLM → restore, the pattern this package exists for.

Run without an API key to see the masking only; set ANTHROPIC_API_KEY to also
send the masked text to Claude and restore the names in the reply.
"""

from __future__ import annotations

import os

from nl_zorg_pii import PiiFilter, example_bsn

TRANSCRIPT = f"""Goedemorgen, u spreekt met Anna de Groot. Ik bel voor mijn vader, dhr. J. de Groot,
geboren 14-03-1951, BSN {example_bsn(7)}. Hij woont op Oosterkade 14, 9711 RS Groningen.
Sinds vannacht heeft hij pijn op de borst die uitstraalt naar zijn linkerarm en hij zweet.
U kunt mij terugbellen op 06-12345678 of mailen naar anna.degroot@example.nl."""


def main() -> None:
    f = PiiFilter()
    masked = f.mask(TRANSCRIPT)

    print("=== Masked (safe to send) ===")
    print(masked.text)
    print("\n=== Mapping (stays on your side) ===")
    for k, v in masked.mapping.items():
        print(f"{k:<20} {v}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n(ANTHROPIC_API_KEY not set; skipping the LLM call.)")
        return

    import anthropic

    client = anthropic.Anthropic()
    reply = client.messages.create(
        model=os.environ.get("MODEL", "claude-sonnet-4-5"),
        max_tokens=400,
        system=(
            "Je bent een assistent voor doktersassistenten. Vat het gesprek samen in de velden "
            "Beller, Patiënt, Klacht, Duur, Alarmsymptomen, Terugbelnummer. Gebruik de "
            "placeholders zoals [NAAM_1] letterlijk; vervang ze niet."
        ),
        messages=[{"role": "user", "content": masked.text}],
    )
    text = "".join(getattr(b, "text", "") for b in reply.content)
    print("\n=== LLM reply (still masked) ===")
    print(text)
    print("\n=== Restored for the practice ===")
    print(PiiFilter.restore(text, masked.mapping))


if __name__ == "__main__":
    main()
