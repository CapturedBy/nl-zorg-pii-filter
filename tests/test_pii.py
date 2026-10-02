import json

import pytest

from nl_zorg_pii import PiiFilter, example_bsn, is_valid_bsn
from nl_zorg_pii.cli import main

BSN_A = example_bsn(1)
BSN_B = example_bsn(2)


class TestBsn:
    def test_generated_numbers_pass_elfproef(self):
        for seed in range(10):
            assert is_valid_bsn(example_bsn(seed))

    def test_distinct_seeds_give_distinct_numbers(self):
        assert BSN_A != BSN_B

    @pytest.mark.parametrize("bad", ["123456789", "000000000", "12345", "abcdefghi", ""])
    def test_invalid(self, bad):
        assert not is_valid_bsn(bad)

    def test_accepts_separators_and_eight_digits(self):
        assert is_valid_bsn(f"{BSN_A[:4]} {BSN_A[4:6]} {BSN_A[6:]}")
        assert is_valid_bsn(f"{BSN_A[:4]}.{BSN_A[4:6]}.{BSN_A[6:]}")
        # 8-digit form of a BSN that starts with 0
        eight = next(
            n for n in (str(i).zfill(9) for i in range(10_000_000, 10_100_000)) if is_valid_bsn(n)
        )
        assert is_valid_bsn(eight[1:])


class TestDetectors:
    def setup_method(self):
        self.f = PiiFilter()

    def example_bsn_only_when_valid(self):
        r = self.f.mask(f"BSN {BSN_A}, dossier 123456789.")
        assert r.text == "BSN [BSN_1], dossier 123456789."

    def test_bsn_with_spaces_and_dots(self):
        spaced = f"{BSN_A[:4]} {BSN_A[4:6]} {BSN_A[6:]}"
        dotted = f"{BSN_A[:4]}.{BSN_A[4:6]}.{BSN_A[6:]}"
        r = self.f.mask(f"nr {spaced} en {dotted}")
        assert r.counts() == {"BSN": 2}
        assert len(r.mapping) == 1  # same value, same placeholder

    def test_email_phone_iban(self):
        r = self.f.mask(
            "Mail j.devries@example.nl of bel 06-12345678 / 050 123 4567. NL91ABNA0417164300."
        )
        assert r.counts() == {"EMAIL": 1, "IBAN": 1, "TELEFOON": 2}
        assert "[TELEFOON_1]" in r.text and "[TELEFOON_2]" in r.text

    def test_phone_does_not_eat_measurements(self):
        r = self.f.mask("Bloeddruk 120/80, temperatuur 38.5, saturatie 97.")
        assert not r.found

    def test_address_and_postcode(self):
        r = self.f.mask("Woont op Van Starkenborghstraat 12a, 9718 EL Groningen.")
        assert r.counts() == {"ADRES": 1, "POSTCODE": 1}
        assert r.text == "Woont op [ADRES_1], [POSTCODE_1] Groningen."

    def test_dob_only_with_cue_by_default(self):
        r = self.f.mask("Geboren 03-05-1971. Consult op 12-09-2026 verliep goed.")
        assert r.counts() == {"GEBOORTEDATUM": 1}
        assert "12-09-2026" in r.text

    def test_dob_textual_month(self):
        r = self.f.mask("geboortedatum: 7 maart 1988")
        assert r.text == "geboortedatum: [GEBOORTEDATUM_1]"

    def test_all_dates_option(self):
        r = PiiFilter(all_dates=True).mask("Consult op 12-09-2026 en 1 januari 2025.")
        assert r.counts() == {"GEBOORTEDATUM": 2}

    def test_name_after_title(self):
        r = self.f.mask("Mevrouw De Jong-Bakker belt; dhr. P. van der Berg ook.")
        assert r.counts() == {"NAAM": 2}
        assert r.mapping["[NAAM_1]"] == "De Jong-Bakker"
        assert r.mapping["[NAAM_2]"] == "P. van der Berg"

    def test_name_after_intro_phrase(self):
        r = self.f.mask("Goedemorgen, u spreekt met Karin Veenstra van de praktijk.")
        assert r.mapping == {"[NAAM_1]": "Karin Veenstra"}
        assert r.text.endswith("[NAAM_1] van de praktijk.")

    def test_name_from_first_name_list(self):
        r = self.f.mask("Anna Jansen heeft koorts; Fatima El Amrani ook.")
        assert [r.mapping[k] for k in sorted(r.mapping)] == ["Anna Jansen", "Fatima El Amrani"]

    def test_trailing_particle_dropped(self):
        r = self.f.mask("Jan van de praktijk belt terug.")
        assert r.mapping["[NAAM_1]"] == "Jan"

    def test_extra_names(self):
        assert not PiiFilter().mask("Xanthippe belt.").found
        assert PiiFilter(extra_names=["Xanthippe"]).mask("Xanthippe belt.").found

    def test_clinical_words_not_names(self):
        r = self.f.mask("Pijn Op De Borst, uitstralend naar de Linkerarm. Advies: Paracetamol.")
        assert not r.found

    def test_kinds_filter(self):
        r = PiiFilter(kinds={"BSN"}).mask(f"Jan Jansen, {BSN_A}, 06-12345678")
        assert r.counts() == {"BSN": 1}


class TestMaskRestore:
    def test_roundtrip(self):
        f = PiiFilter()
        src = f"Patiënt Jan de Vries ({BSN_A}) belt, 06-12345678, geboren 1-1-1980."
        r = f.mask(src)
        assert r.text == "Patiënt [NAAM_1] ([BSN_1]) belt, [TELEFOON_1], geboren [GEBOORTEDATUM_1]."
        assert PiiFilter.restore(r.text, r.mapping) == src

    def test_restore_in_llm_reply(self):
        f = PiiFilter()
        r = f.mask("Mevrouw Pietersen heeft hoofdpijn.")
        reply = "Samenvatting: [NAAM_1] meldt hoofdpijn. Advies aan [NAAM_1]: paracetamol."
        assert (
            PiiFilter.restore(reply, r.mapping)
            == "Samenvatting: Pietersen meldt hoofdpijn. Advies aan Pietersen: paracetamol."
        )

    def test_unknown_placeholder_left_alone(self):
        assert PiiFilter.restore("[NAAM_9] en [BSN_3]", {}) == "[NAAM_9] en [BSN_3]"

    def test_redact(self):
        f = PiiFilter()
        assert f.redact(f"BSN {BSN_A} van Anna") == "BSN [BSN] van [NAAM]"
        assert f.redact(f"BSN {BSN_A}", token="***") == "BSN ***"

    def test_no_pii_is_unchanged(self):
        text = "Patiënt meldt sinds twee dagen keelpijn zonder koorts."
        r = PiiFilter().mask(text)
        assert r.text == text and not r.found and r.mapping == {}


class TestCli:
    def test_mask_and_restore(self, tmp_path, capsys):
        src = tmp_path / "in.txt"
        src.write_text(f"Dhr. Bakker, BSN {BSN_A}.", encoding="utf-8")
        mapping = tmp_path / "map.json"
        assert main(["mask", str(src), "--mapping", str(mapping)]) == 0
        masked = capsys.readouterr().out
        assert masked == "Dhr. [NAAM_1], BSN [BSN_1]."
        assert json.loads(mapping.read_text())["[BSN_1]"] == BSN_A

        reply = tmp_path / "reply.txt"
        reply.write_text("Advies voor [NAAM_1].", encoding="utf-8")
        assert main(["restore", str(reply), "--mapping", str(mapping)]) == 0
        assert capsys.readouterr().out == "Advies voor Bakker."

    def test_check_exit_code(self, tmp_path, capsys):
        clean = tmp_path / "clean.txt"
        clean.write_text("Keelpijn sinds gisteren.", encoding="utf-8")
        assert main(["check", str(clean)]) == 0
        dirty = tmp_path / "dirty.txt"
        dirty.write_text(f"BSN {BSN_A}", encoding="utf-8")
        assert main(["check", str(dirty)]) == 1
        assert "BSN" in capsys.readouterr().out
