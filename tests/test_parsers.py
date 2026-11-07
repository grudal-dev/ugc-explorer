from datetime import date

from ugcx import allocine, match, ugc
from ugcx.text import departement, norm

UGC_HTML = """
<html><body><header><ul><li>Menu 75001 Paris</li></ul></header><main>
<h2 id="r1">Paris</h2>
<h3 id="classic-r1">Cinémas UGC</h3>
<ul>
 <li><a href="/cinema-ugc-cine-cite-bercy.html"><span>UGC Ciné Cité Bercy</span>
     <span>2, cour Saint-Emilion</span><span>75012 Paris</span></a></li>
 <li><a href="/cinema-ugc-montparnasse.html">UGC Montparnasse 83, bd du Montparnasse 75006 Paris</a></li>
</ul>
<h3 id="partner-r1">Cinémas partenaires</h3>
<ul>
 <li>MK2 BEAUBOURG<br>50, rue Rambuteau<br>75003 PARIS</li>
 <li><p>LE GRAND REX</p><p>1, boulevard Poissonnière</p><p>75002 Paris</p></li>
</ul>
<h2 id="region-3">Strasbourg</h2>
<p>LE STAR<br>27, rue du Jeu des Enfants<br>67000 STRASBOURG<br><br>
   LE STAR SAINT-EXUPÉRY<br>18, rue du 22 Novembre<br>67000 STRASBOURG</p>
<p>Les cinémas partenaires peuvent ne pas accepter la carte dématérialisée.</p>
</main><footer><li>UGC, 24 avenue Charles de Gaulle 92200 Neuilly</li></footer></body></html>
"""


def test_ugc_parse_variants():
    cs = {c["name"]: c for c in ugc.parse(UGC_HTML)}
    assert set(cs) == {"UGC Ciné Cité Bercy", "UGC Montparnasse", "MK2 Beaubourg", "Le Grand Rex",
                       "Le Star", "Le Star Saint-Exupéry"}, cs.keys()
    b = cs["UGC Ciné Cité Bercy"]
    assert b["postcode"] == "75012" and b["group"] == "UGC" and b["address"] == "2, cour Saint-Emilion"
    assert b["ugcUrl"] == "https://www.ugc.fr/cinema-ugc-cine-cite-bercy.html"
    assert cs["UGC Montparnasse"]["address"].startswith("83")
    assert cs["MK2 Beaubourg"]["group"] == "mk2"
    assert cs["Le Grand Rex"]["group"] == "Partenaire" and cs["Le Grand Rex"]["postcode"] == "75002"
    assert cs["Le Star Saint-Exupéry"]["zone"] == "Strasbourg"
    assert cs["Le Star"]["dept"] == "67"


def test_departement():
    assert departement("75012") == "75"
    assert departement("20000") == "2A" and departement("20200") == "2B"
    assert departement("97400") == "974"


THEATERS_HTML = """
<div class="theater-card"><a class="add-theater-anchor" data-theater="{&quot;id&quot;:&quot;C0026&quot;,&quot;name&quot;:&quot;UGC Cin&#233; Cit&#233; Bercy&quot;}"></a>
<address>2, cour Saint-Emilion 75012 Paris</address></div>
<div class="theater-card"><a data-theater="{&quot;id&quot;:&quot;C0050&quot;,&quot;name&quot;:&quot;Path&#233; Bercy&quot;}"></a>
<address>5 rue X 75012 Paris</address></div>
"""


def test_theater_cards_and_match():
    ts = allocine.parse_theater_cards(THEATERS_HTML)
    assert [t["id"] for t in ts] == ["C0026", "C0050"]
    assert ts[0]["name"] == "UGC Ciné Cité Bercy" and ts[0]["postcode"] == "75012"
    c = {"name": "UGC Ciné Cité Bercy", "address": "2, cour Saint-Emilion", "postcode": "75012", "dept": "75"}
    best, s = match.best_match(c, ts)
    assert best["id"] == "C0026" and s > 0.9
    nope = {"name": "Le Balzac", "address": "1 rue Balzac", "postcode": "75012", "dept": "75"}
    assert match.best_match(nope, ts)[0] is None


def test_departement_links():
    html = ('<a href="/salle/cinema/departement-83191/" title="Bouches-du-Rhône">x</a>'
            '<a href="/salle/cinema/departement-83178/">Paris</a>'
            '<a href="/salle/cinema/ville-115755/" title="Paris">Paris</a>')
    ids = allocine.parse_departement_links(html)
    assert ids == {"13": "departement-83191", "75": "departement-83178"}


def test_compact_showtimes():
    raw = [{
        "movie": {"internalId": 1001, "title": "Film", "runtime": "1h 52min",
                  "poster": {"url": "https://x/p.jpg"}, "genres": [{"translate": "Drame"}],
                  "stats": {"userRating": {"score": 4.1, "count": 250}},
                  "credits": [{"position": {"name": "DIRECTOR"}, "person": {"firstName": "Jane", "lastName": "Doe"}}]},
        "showtimes": {
            "original": [{"internalId": 1, "startsAt": "2026-11-07T20:00:00", "diffusionVersion": "ORIGINAL",
                          "projection": ["DIGITAL"], "experience": ["IMAX"],
                          "data": {"ticketing": [{"urls": ["https://t/1"]}]}}],
            "local": [{"internalId": 2, "startsAt": "2026-11-07T14:00:00", "diffusionVersion": "LOCAL"}],
            "multiple": [{"internalId": 1, "startsAt": "2026-11-07T20:00:00", "diffusionVersion": "ORIGINAL"}],
        }}]
    movies, shows = allocine.compact_showtimes(raw)
    assert movies["1001"]["directors"] == ["Jane Doe"] and movies["1001"]["rating"] == 4.1
    assert [(s["t"], s["v"]) for s in shows] == [("14:00", "VF"), ("20:00", "VO")]
    assert shows[1]["f"] == ["IMAX"] and shows[1]["u"] == "https://t/1"


def test_norm():
    assert norm("Ciné Cité  Bercy !") == "cine cite bercy"
    assert date(2026, 1, 1)
