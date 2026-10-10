#!/usr/bin/env python3
"""Render README screenshots via Playwright page.set_content() with the built
CSS inlined (sandbox Chromium cannot reach external HTTPS; loopback is
blocked). The page shell comes from the real SSR HTML of the running app;
the screening card is rendered from the real /api/v1/screen payload."""
import json, re, urllib.request, urllib.parse, html as htmlmod

import base64, glob, os

BASE = "http://localhost:3127"
ROOT = "/home/hatch/workspace/toronto-tree-canopy"
OUT = os.path.join(ROOT, "public/screenshots")
DEMO_ADDRESS = "1843 Eglinton Ave W"

def find_css():
    cands = glob.glob(os.path.join(ROOT, ".next", "static", "**", "*.css"), recursive=True)
    assert cands, "no built CSS found under .next/static"
    # The global stylesheet is the largest css chunk.
    return max(cands, key=os.path.getsize)

CSS_PATH = find_css()

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.read().decode("utf-8")


def parcel_map_html(parcel_id, labels):
    """The real map block: <img> of the PIL-rendered canopy PNG (inlined as a
    data URI because page.set_content() has no server for /parcels/...)."""
    png = os.path.join(ROOT, "public", "parcels", f"{parcel_id}.png")
    with open(png, "rb") as fh:
        uri = "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    legend = f'''<div class="maplegend maplegend-overlay">
<span><span class="sw" style="background:rgba(46,125,50,0.45);border:2px solid #2e7d32"></span>{labels["legend_tall"]}</span>
<span><span class="swsq"></span>{labels["legend_parcel"]}</span>
<span><span class="swdash"></span>{labels["legend_buffer"]}</span>
</div>'''
    return f'''<div class="mapwrap"><h3>{labels["map_title"]}</h3>
<div class="parcelmap"><img src="{uri}" alt="{labels["map_title"]}"/>{legend}</div>
</div>'''

def pct(p):
    return f"{round(p*100)}%"

def m2(v):
    return f"{round(v)}" if v >= 100 else f"{v:.1f}"

def esc(s):
    return htmlmod.escape(str(s))

def card_html(d, L):
    method_line = L["method_line"].format(auc=f'{d["method"]["calibration_auc"]:.2f}',
                                          n=f'{d["method"]["calibration_n"]:,}')
    maxh = d["lot"]["max_chm_m"]
    bmaxh = d["neighbour_6m"]["max_chm_m"]
    return f'''<article class="screencard">
<div class="screencard-head"><h2 class="display">{L["lot_label"]}: {esc(d["address"])}</h2>
<div class="screencard-meta"><span>{L["parcel_id"]}: <code>{esc(d["parcel_id"])}</code></span>
<span>{L["imagery_vintage"]}: <strong>{esc(d["imagery_vintage"])}</strong></span>
<span>{esc(d["pilot_scope"])}</span></div></div>
<p class="verdict">{esc(d["verdict"])}</p>
<div class="statgrid">
<div class="stat"><div class="k">{L["tall_canopy_area"]}</div><div class="v">{m2(d["lot"]["tall_canopy_m2_ge8"])}<small> m²</small></div></div>
<div class="stat"><div class="k">{L["max_height"]}</div><div class="v">{maxh if maxh is not None else "–"}<small> m</small></div></div>
<div class="stat"><div class="k">{L["canopy_cover"]}</div><div class="v">{d["lot"]["canopy_pct"]}<small>%</small></div></div>
<div class="stat"><div class="k">{L["p_any_mature"]}</div><div class="v">{pct(d["lot"]["p_any_ge_30cm"])}</div></div>
<div class="stat"><div class="k">{L["p_any_distinctive"]}</div><div class="v">{pct(d["lot"]["p_any_distinctive"])}</div></div>
</div>
{parcel_map_html(d["parcel_id"], L)}
<div class="neighbour"><h3>{L["neighbour_title"]}</h3><p class="dim">{L["neighbour_why"]}</p>
<div class="nbstats">
<div><div class="dim">{L["tall_canopy_area"]}</div><div class="v">{m2(d["neighbour_6m"]["tall_canopy_m2_ge8"])} m²</div></div>
<div><div class="dim">{L["max_height"]}</div><div class="v">{bmaxh if bmaxh is not None else "–"} m</div></div>
<div><div class="dim">{L["p_any_mature"]}</div><div class="v">{pct(d["neighbour_6m"]["p_any_ge_30cm"])}</div></div>
<div><div class="dim">{L["p_any_distinctive"]}</div><div class="v">{pct(d["neighbour_6m"]["p_any_distinctive"])}</div></div>
</div></div>
<div class="honesty"><p class="methodline">{esc(method_line)}</p>
<p>{esc(L["honesty"])}</p><p>{esc(L["vintage_caveat"])}</p><p>{esc(L["next_step"])}</p></div>
</article>'''

EN = {
    "lot_label": "Lot", "parcel_id": "Parcel", "imagery_vintage": "Canopy vintage",
    "tall_canopy_area": "Tall canopy (8 m and up)", "max_height": "Tallest surface",
    "canopy_cover": "Tall-canopy cover",
    "p_any_mature": "Chance of a mature tree (30 cm+)", "p_any_distinctive": "Chance of a Distinctive tree (61 cm+)",
    "neighbour_title": "Neighbouring tall canopy (within 6 m of the boundary)",
    "neighbour_why": "The by-law site plan must show all trees 30 cm and up on adjacent properties within 6 m of the boundary, so the screen measures the 6 m band around the lot too.",
    "method_line": "Mature-tree calibration AUC {auc}, fit on {n} Ward 12 street trees with known trunk diameters against their LiDAR height and canopy area.",
    "honesty": "Screening signal only; not a permit determination. The tall-canopy numbers measure elevated surface 6 m and up from 2023 LiDAR: trees and tall structures such as buildings read the same. The mature-tree chance is a statistical calibration fit on the City's street-tree inventory (managed road-allowance trees, pruned and spaced by the City), applied to tree-like LiDAR peaks on the lot; peaks smoother than 95% of measured street-tree crowns are treated as roofs and excluded, but pitched roofs still read as canopy. The City's Private Tree By-law (Municipal Code Chapter 813, Article III) requires a permit before injuring or removing any private tree 30 cm or more in trunk diameter, measured at 1.4 m; the September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Only a certified arborist can confirm trunk diameter on site.",
    "vintage_caveat": "Canopy structure is from 2023 LiDAR. Trees removed after that are invisible to this screen, and growth since then is missing too.",
    "next_step": "Get an arborist report before planning around these numbers.",
    "map_title": "Tall-canopy map",
    "legend_tall": "tall canopy (8 m and up, 2023 LiDAR)",
    "legend_parcel": "parcel boundary", "legend_buffer": "6 m neighbour buffer",
}

FR = {
    "lot_label": "Lot", "parcel_id": "Parcelle", "imagery_vintage": "Millésime de la canopée",
    "tall_canopy_area": "Canopée haute (8 m et plus)", "max_height": "Surface la plus haute",
    "canopy_cover": "Couvert de canopée haute",
    "p_any_mature": "Probabilité d'un arbre mature (30 cm+)", "p_any_distinctive": "Probabilité d'un arbre Distinctive (61 cm+)",
    "neighbour_title": "Canopée haute voisine (à moins de 6 m de la limite)",
    "neighbour_why": "Le plan de situation exigé par le règlement doit montrer tous les arbres de 30 cm et plus sur les propriétés adjacentes à moins de 6 m de la limite; le dépistage mesure donc aussi la bande de 6 m autour du lot.",
    "method_line": "AUC de calibrage des arbres matures : {auc}, ajustée sur {n} arbres de rue du quartier 12 au diamètre connu, selon leur hauteur LiDAR et leur superficie de canopée.",
    "honesty": "Signal de dépistage seulement; ce n'est pas une décision de permis. Les chiffres de canopée haute mesurent la surface élevée à 6 m et plus d'après le LiDAR de 2023 : les arbres et les structures hautes comme les bâtiments s'y lisent de la même façon. La probabilité d'arbre mature est un calibrage statistique ajusté sur l'inventaire des arbres de rue de la Ville (arbres d'emprise gérés, taillés et espacés par la Ville), appliqué aux pics LiDAR d'allure arborée du lot; les pics plus lisses que 95 % des couronnes d'arbres de rue mesurées sont traités comme des toits et exclus, mais les toits en pente se lisent encore comme de la canopée. Le règlement sur les arbres privés de la Ville (chapitre 813 du Code municipal, article III) exige un permis avant d'endommager ou d'abattre tout arbre privé de 30 cm ou plus de diamètre, mesuré à 1,4 m; les modifications de septembre 2026 ont ajouté une catégorie Distinctive au-delà de 61 cm avec des protections renforcées. Seul un arboriste certifié peut confirmer le diamètre du tronc sur place.",
    "vintage_caveat": "La structure de la canopée date du LiDAR de 2023. Les arbres abattus depuis sont invisibles à ce dépistage, et la croissance récente y manque aussi.",
    "next_step": "Obtenez un rapport d'arboriste avant de planifier autour de ces chiffres.",
    "map_title": "Carte de la canopée haute",
    "legend_tall": "canopée haute (8 m et plus, LiDAR 2023)",
    "legend_parcel": "limite de la parcelle", "legend_buffer": "zone tampon de 6 m",
}

def build_page(lang):
    page_html = get(f"/{lang}")
    css = open(CSS_PATH).read()
    page_html = re.sub(r'<link rel="stylesheet"[^>]*>', f"<style>{css}</style>", page_html, count=1)
    data = json.loads(get(f"/api/v1/screen?address={urllib.parse.quote(DEMO_ADDRESS)}&lang={lang}"))
    L = EN if lang == "en" else FR
    card = card_html(data, L)
    # Replace the "no screen yet" placeholder with the rendered card.
    page_html, n = re.subn(
        r'<div><p class="examples" style="margin-top:24px">.*?</p></div>',
        f"<div>{card}</div>", page_html, count=1)
    assert n == 1, f"placeholder not found for {lang}"
    # Pre-fill the search input value for the screenshot.
    page_html = page_html.replace('value=""', f'value="{DEMO_ADDRESS}"', 1)
    return page_html

def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for lang in ("en", "fr"):
            page_html = build_page(lang)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_content(page_html, wait_until="load")
            page.wait_for_timeout(400)
            page.screenshot(path=f"{OUT}/explorer-{lang}.png", full_page=True)
            card = page.locator(".screencard")
            card.screenshot(path=f"{OUT}/card-{lang}.png")
            page.close()
        browser.close()
    print("screenshots written to", OUT)

if __name__ == "__main__":
    main()
