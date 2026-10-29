"""reference/hiv_drugs.csv against Lifei's verified File 06 lists (commit e06303d)."""
from __future__ import annotations

from runner import config

LIFEI_INGREDIENTS = set(
    "abacavir|amprenavir|atazanavir|bictegravir|cabotegravir|cobicistat|darunavir|delavirdine|"
    "didanosine|dolutegravir|doravirine|efavirenz|elvitegravir|emtricitabine|enfuvirtide|etravirine|"
    "fosamprenavir|fostemsavir|ibalizumab|indinavir|islatravir|lenacapavir|leronlimab|lopinavir|"
    "maraviroc|nelfinavir|nevirapine|raltegravir|rilpivirine|ritonavir|saquinavir|stavudine|tenofovir|"
    "tipranavir|zalcitabine|zidovudine".split("|"))
LIFEI_BRANDS = set(
    "agenerase|apretude|aptivus|atripla|biktarvy|cabenuva|cimduo|combivir|complera|crixivan|delstrigo|"
    "descovy|dovato|edurant|emtriva|epzicom|evotaz|fortovase|fuzeon|genvoya|hivid|intelence|invirase|"
    "isentress|juluca|kaletra|lexiva|norvir|odefsey|pifeltro|prezcobix|prezista|pro 140|rescriptor|"
    "retrovir|reyataz|rukobia|selzentry|stribild|sunlenca|sustiva|symfi|symtuza|temixys|tivicay|triumeq|"
    "trizivir|trogarzo|truvada|tybost|vemlidy|videx|viracept|viramune|viread|vitekta|vocabria|zerit|ziagen"
    .split("|"))
PI_EXCLUDED_INGREDIENTS = {"ritonavir", "tenofovir", "emtricitabine", "cabotegravir", "lenacapavir"}
PI_EXCLUDED_BRANDS = {"norvir", "truvada", "descovy", "apretude", "viread", "vemlidy", "emtriva",
                      "sunlenca", "vocabria", "cimduo", "temixys"}


def test_identifying_ingredients_are_lifeis_list_minus_the_pi_exclusions() -> None:
    assert set(config.hiv_identifying_regex("ingredient").split("|")) == LIFEI_INGREDIENTS - PI_EXCLUDED_INGREDIENTS


def test_identifying_brands_are_lifeis_list_minus_brands_made_only_of_excluded_drugs() -> None:
    assert set(config.hiv_identifying_regex("brand").split("|")) == LIFEI_BRANDS - PI_EXCLUDED_BRANDS


def test_every_state_has_a_census_region_and_anything_else_is_other() -> None:
    sql = config.census_region_sql("s")
    assert sql.count("'Northeast'") == sql.count("'Midwest'") == sql.count("'South'") == sql.count("'West'") == 1
    assert sum(1 for row in config.read_reference("census_regions.csv")) == 51
    assert "ELSE 'Other'" in sql
