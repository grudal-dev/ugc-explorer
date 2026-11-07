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
                          "projection": ["DIGITAL", "F_35MM"], "experience": ["IMAX"], "sound": ["DOLBY_71"],
                          "data": {"ticketing": [{"urls": ["https://t/1"]}]}}],
            "local": [{"internalId": 2, "startsAt": "2026-11-07T14:00:00", "diffusionVersion": "LOCAL"}],
            "multiple": [{"internalId": 1, "startsAt": "2026-11-07T20:00:00", "diffusionVersion": "ORIGINAL"}],
        }}]
    movies, shows = allocine.compact_showtimes(raw)
    assert movies["1001"]["directors"] == ["Jane Doe"] and movies["1001"]["rating"] == 4.1
    assert [(s["t"], s["v"]) for s in shows] == [("14:00", "VF"), ("20:00", "VO")]
    assert shows[1]["f"] == ["35mm", "IMAX"] and shows[1]["u"] == "https://t/1"


def test_norm():
    assert norm("Ciné Cité  Bercy !") == "cine cite bercy"
    assert date(2026, 1, 1)


REAL_MARKUP = """
<h2 class="color--dark-blue">Paris</h2>
<a href="#classic-r1" aria-controls="classic-r1" class="accordion-title"><span>Cinémas UGC</span></a>
<div class="row collapse" id="classic-r1">
 <div class="col"><a href="cinema-ugc-cine-cite-bercy.html"><div class="item--cinema">
  <div class="item--cinema-content text-center">
   <div class="color--white text-uppercase">UGC Cin&eacute; Cit&eacute; Bercy</div>
   <div class="color--blue-grey">2, cour Saint Emilion<br>75012&nbsp;PARIS</div>
  </div></div></a></div>
</div>
<a href="#partner-r1" aria-controls="partner-r1" class="accordion-title"><span>Cinémas partenaires</span></a>
<div class="row collapse" id="partner-r1">
 <div class="item--cinema"><div class="item--cinema-content">
   <div class="color--white text-uppercase">MK2 BEAUBOURG</div>
   <div class="color--blue-grey">50, rue Rambuteau<br>75003&nbsp;PARIS</div></div></div>
</div>
<a href="#region-3" aria-controls="region-3" class="accordion-title"><span class="text-uppercase">Bordeaux</span></a>
<div class="row collapse" id="region-3">
 <div class="item--cinema"><div class="item--cinema-content">
   <div class="color--white text-uppercase">GRAND ÉCRAN LIBOURNE</div>
   <div class="color--blue-grey">56 avenue Gallieni<br>33500&nbsp;LIBOURNE</div></div></div>
</div>
"""


def test_ugc_structured_markup():
    cs = {c["name"]: c for c in ugc.parse_structured(REAL_MARKUP)}
    b = cs["UGC Ciné Cité Bercy"]
    assert (b["group"], b["zone"], b["city"], b["address"]) == ("UGC", "Paris", "Paris", "2, cour Saint Emilion")
    assert b["ugcUrl"] == "https://www.ugc.fr/cinema-ugc-cine-cite-bercy.html"
    assert cs["MK2 Beaubourg"]["group"] == "mk2"
    lib = cs["Grand Écran Libourne"]
    assert (lib["group"], lib["zone"], lib["postcode"]) == ("Partenaire", "Bordeaux", "33500")


def test_assign_unique_and_same_street():
    ts = [
        {"id": "P0086", "name": "UGC Ciné Cité Lille", "address": "40 rue de Béthune 59800 Lille", "postcode": "59800", "dept": "59"},
        {"id": "P0001", "name": "Majestic Lille", "address": "54 rue de Béthune 59000 Lille", "postcode": "59000", "dept": "59"},
        {"id": "P0170", "name": "Limoges Centre", "address": "11, place Denis-Dussoubs 87000 Limoges", "postcode": "87000", "dept": "87"},
    ]
    cs = [
        {"id": "a", "name": "UGC Ciné Cité Lille", "address": "40 rue de Béthune", "postcode": "59000", "dept": "59"},
        {"id": "b", "name": "Le Majestic", "address": "54 rue de Béthune", "postcode": "59000", "dept": "59"},
        {"id": "c", "name": "Horizon Grand Ecran", "address": "9 - 11, Place Denis Dussoubs", "postcode": "87100", "dept": "87"},
    ]
    res = match.assign(cs, ts)
    assert {k: v[0]["id"] for k, v in res.items()} == {"a": "P0086", "b": "P0001", "c": "P0170"}
