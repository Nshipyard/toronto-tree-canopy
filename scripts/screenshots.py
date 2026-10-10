#!/usr/bin/env python3
"""Render README screenshots via Playwright page.set_content() with the built
CSS inlined (sandbox Chromium cannot reach external HTTPS; loopback is
blocked). The page shell comes from the real SSR HTML of the running app;
the screening card is rendered from the real /api/v1/screen payload."""
import json, re, urllib.request, html as htmlmod

import base64, glob, os

BASE = "http://localhost:3127"
ROOT = "/home/hatch/workspace/toronto-tree-canopy"
OUT = os.path.join(ROOT, "public/screenshots")

def find_css():
    cands = glob.glob(os.path.join(ROOT, ".next", "static", "**", "*.css"), recursive=True)
    assert cands, "no built CSS found under .next/static"
    # The global stylesheet is the largest css chunk.
    return max(cands, key=os.path.getsize)

CSS_PATH = find_css()

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.read().decode("utf-8")


def parcel_map_html(parcel_id, sample, labels):
    """The real map block: <img> of the PIL-rendered aerial PNG (inlined as a
    data URI because page.set_content() has no server for /parcels/...)."""
    png = os.path.join(ROOT, "public", "parcels", f"{parcel_id}.png")
    with open(png, "rb") as fh:
        uri = "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    if sample:
        legend = f'''<div class="maplegend">
<span><span class="swsq"></span>{labels["legend_parcel"]}</span>
<span><span class="swdash"></span>{labels["legend_buffer"]}</span>
</div>'''
        return f'''<div class="mapwrap"><h3>{labels["map_title"]}</h3>
<div class="parcelmap"><img src="{uri}" alt="{labels["map_title"]}"/></div>
{legend}</div>'''
    legend = f'''<div class="maplegend maplegend-overlay">
<span><span class="sw" style="background:rgba(216,6,33,0.35);border:2px solid #d80621"></span>{labels["legend_mature"]}</span>
<span><span class="sw" style="background:rgba(46,125,50,0.35);border:2px solid #2e7d32"></span>{labels["legend_possible"]}</span>
<span><span class="swsq"></span>{labels["legend_parcel"]}</span>
<span><span class="swdash"></span>{labels["legend_buffer"]}</span>
</div>'''
    return f'''<div class="mapwrap"><h3>{labels["map_title"]}</h3>
<div class="parcelmap"><img src="{uri}" alt="{labels["map_title"]}"/>{legend}</div>
</div>'''
def pct(p):
    return f"{round(p*100)}%"

def esc(s):
    return htmlmod.escape(str(s))

def card_html(d, L):
    sample = f'<div class="samplebanner">{esc(L["sample_banner"])}</div>' if d["method"]["sample"] else ""
    crowns = ""
    for i, c in enumerate(d["lot"]["crowns"]):
        if c["p_ge_30cm"] >= 0.5:
            badge = f'<span class="badge mature">{L["likely_mature"]}</span>'
        elif c["p_ge_30cm"] >= 0.2:
            badge = f'<span class="badge possible">{L["maybe_mature"]}</span>'
        else:
            badge = f'<span class="badge young">{L["young"]}</span>'
        crowns += f'''<div class="crownrow"><div class="crown-name">{L["crown_label"].format(i=i+1)}{badge}</div>
<div>{L["crown_diameter"]}: <strong>{c["crown_diameter_m"]} m</strong>
<div class="dim">{L["dbh_estimate"]}: <strong>{c["dbh_est_cm"]} cm</strong> ({L["pi95"]}: {c["dbh_pi95"][0]}-{c["dbh_pi95"][1]} cm)</div></div>
<div>{L["p_ge30"]}: <strong>{pct(c["p_ge_30cm"])}</strong>
<div class="dim">{L["p_gt61"]}: <strong>{pct(c["p_gt_61cm"])}</strong></div></div></div>'''
    crownlist = f'<div class="crownlist"><h3>{L["crown_list_title"]}</h3>{crowns}</div>' if crowns else ""
    fee = f'<div class="feeline">{esc(d["fee_line"])}</div>' if d.get("fee_line") else ""
    method_line = L["sample_method"] if d["method"]["sample"] else L["method_line"].format(f1=f'{d["method"]["detection_f1"]:.2f}')
    return f'''<article class="screencard">
{sample}
<div class="screencard-head"><h2 class="display">{L["lot_label"]}: {esc(d["address"])}</h2>
<div class="screencard-meta"><span>{L["parcel_id"]}: <code>{esc(d["parcel_id"])}</code></span>
<span>{L["imagery_vintage"]}: <strong>{esc(d["imagery_vintage"])}</strong></span>
<span>{esc(d["pilot_scope"])}</span></div></div>
<p class="verdict">{esc(d["verdict"])}</p>
<div class="statgrid">
<div class="stat"><div class="k">{L["crowns_detected"]}</div><div class="v">{d["lot"]["crown_count"]}</div></div>
<div class="stat"><div class="k">{L["canopy_cover"]}</div><div class="v">{d["lot"]["canopy_pct"]}<small>%</small></div></div>
<div class="stat"><div class="k">{L["p_any_mature"]}</div><div class="v">{pct(d["lot"]["p_any_ge_30cm"])}</div></div>
<div class="stat"><div class="k">{L["p_any_distinctive"]}</div><div class="v">{pct(d["lot"]["p_any_distinctive"])}</div></div>
</div>
{parcel_map_html(d["parcel_id"], d["method"]["sample"], L)}
{crownlist}
<div class="neighbour"><h3>{L["neighbour_title"]}</h3><p class="dim">{L["neighbour_why"]}</p>
<div class="nbstats">
<div><div class="dim">{L["crowns_detected"]}</div><div class="v">{d["neighbour_6m"]["crown_count"]}</div></div>
<div><div class="dim">{L["p_any_mature"]}</div><div class="v">{pct(d["neighbour_6m"]["p_any_ge_30cm"])}</div></div>
<div><div class="dim">{L["p_any_distinctive"]}</div><div class="v">{pct(d["neighbour_6m"]["p_any_distinctive"])}</div></div>
</div></div>
{fee}
<div class="honesty"><p class="methodline">{esc(method_line)}</p>
<p>{esc(L["honesty"])}</p><p>{esc(L["vintage_caveat"])}</p><p>{esc(L["next_step"])}</p></div>
</article>'''

EN = {
    "lot_label": "Lot", "parcel_id": "Parcel", "imagery_vintage": "Imagery vintage",
    "crowns_detected": "Crowns detected", "canopy_cover": "Canopy cover",
    "p_any_mature": "Chance any crown clears 30 cm", "p_any_distinctive": "Chance any crown clears 61 cm",
    "neighbour_title": "Neighbouring crowns (within 6 m of the boundary)",
    "neighbour_why": "The by-law site plan must show all trees 30 cm and up on adjacent properties within 6 m of the boundary, so the screen counts crowns across that line too.",
    "crown_list_title": "Detected crowns", "crown_label": "Crown {i}",
    "crown_diameter": "Crown diameter", "dbh_estimate": "Estimated trunk diameter (DBH)",
    "pi95": "95% prediction interval", "p_ge30": "Chance trunk is 30 cm or more",
    "p_gt61": "Chance trunk is over 61 cm (Distinctive tier)",
    "likely_mature": "likely mature", "maybe_mature": "possible", "young": "young",
    "sample_banner": "Sample data. These parcels are synthetic placeholders so the app can run; the Ward 12 pilot will replace them with measured detections.",
    "sample_method": "Detection F1 shown is a sample placeholder; the pilot has not measured its own accuracy yet.",
    "method_line": "Detection F1 {f1}, measured on hand-labeled pilot tiles (pilot number pending).",
    "honesty": "Screening signal only; not a permit determination. The City's Private Tree By-law (Municipal Code Chapter 813, Article III) requires a permit before injuring or removing any private tree 30 cm or more in trunk diameter, measured at 1.4 m; the September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Only a certified arborist can confirm trunk diameter on site.",
    "vintage_caveat": "Imagery is from 2022. Trees removed after that are invisible to this screen, and new growth since then is missing too.",
    "next_step": "Get an arborist report before planning around these crowns.",
    "map_title": "Crown map", "scale": "10 m",
    "legend_mature": "crown likely 30 cm or more (probability at least 50%)",
    "legend_possible": "crown possible", "legend_parcel": "parcel boundary", "legend_buffer": "6 m neighbour buffer",
}

FR = {
    "lot_label": "Lot", "parcel_id": "Parcelle", "imagery_vintage": "Millésime des images",
    "crowns_detected": "Couronnes détectées", "canopy_cover": "Couvert de canopée",
    "p_any_mature": "Probabilité qu'une couronne atteigne 30 cm", "p_any_distinctive": "Probabilité qu'une couronne dépasse 61 cm",
    "neighbour_title": "Couronnes voisines (à moins de 6 m de la limite)",
    "neighbour_why": "Le plan de situation exigé par le règlement doit montrer tous les arbres de 30 cm et plus sur les propriétés adjacentes à moins de 6 m de la limite; le dépistage compte donc aussi les couronnes de l'autre côté de cette ligne.",
    "crown_list_title": "Couronnes détectées", "crown_label": "Couronne {i}",
    "crown_diameter": "Diamètre de la couronne", "dbh_estimate": "Diamètre du tronc estimé (DHP)",
    "pi95": "Intervalle de prédiction à 95 %", "p_ge30": "Probabilité que le tronc atteigne 30 cm ou plus",
    "p_gt61": "Probabilité que le tronc dépasse 61 cm (catégorie Distinctive)",
    "likely_mature": "probablement mature", "maybe_mature": "possible", "young": "jeune",
    "sample_banner": "Données d'exemple. Ces parcelles sont des substituts synthétiques pour faire fonctionner l'application; le projet pilote du quartier 12 les remplacera par des détections mesurées.",
    "sample_method": "Le F1 de détection affiché est une valeur d'exemple; le pilote n'a pas encore mesuré sa propre précision.",
    "method_line": "F1 de détection {f1}, mesuré sur des tuiles étiquetées à la main du projet pilote (chiffre du pilote à venir).",
    "honesty": "Signal de dépistage seulement; ce n'est pas une décision de permis. Le règlement sur les arbres privés de la Ville (chapitre 813 du Code municipal, article III) exige un permis avant d'endommager ou d'abattre tout arbre privé de 30 cm ou plus de diamètre, mesuré à 1,4 m; les modifications de septembre 2026 ont ajouté une catégorie Distinctive au-delà de 61 cm avec des protections renforcées. Seul un arboriste certifié peut confirmer le diamètre du tronc sur place.",
    "vintage_caveat": "Les images datent de 2022. Les arbres abattus depuis sont invisibles à ce dépistage, et la croissance récente y manque aussi.",
    "next_step": "Obtenez un rapport d'arboriste avant de planifier autour de ces couronnes.",
    "map_title": "Carte des couronnes", "scale": "10 m",
    "legend_mature": "couronne probablement de 30 cm ou plus (probabilité d'au moins 50 %)",
    "legend_possible": "couronne possible", "legend_parcel": "limite de la parcelle", "legend_buffer": "zone tampon de 6 m",
}

def build_page(lang):
    page_html = get(f"/{lang}")
    css = open(CSS_PATH).read()
    page_html = re.sub(r'<link rel="stylesheet"[^>]*>', f"<style>{css}</style>", page_html, count=1)
    data = json.loads(get(f"/api/v1/screen?address=407%20Arlington%20Ave&lang={lang}"))
    L = EN if lang == "en" else FR
    card = card_html(data, L)
    # Replace the "no screen yet" placeholder with the rendered card.
    page_html, n = re.subn(
        r'<div><p class="examples" style="margin-top:24px">.*?</p></div>',
        f"<div>{card}</div>", page_html, count=1)
    assert n == 1, f"placeholder not found for {lang}"
    # Pre-fill the search input value for the screenshot.
    page_html = page_html.replace('value=""', 'value="407 Arlington Ave"', 1)
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
