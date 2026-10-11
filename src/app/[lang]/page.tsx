import Link from "next/link";
import Explorer from "@/components/Explorer";
import DownloadPicker from "@/components/DownloadPicker";
import McpConnect from "@/components/McpConnect";
import { LANGS, STRINGS, pickLang } from "@/lib/i18n";
import { loadCalibration } from "@/lib/canopy";

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

function MapleLeaf() {
  return (
    <svg viewBox="-1860 -2000 3720 4030" width="26" height="28" fill="#d80621" aria-hidden="true">
      <path d="m-90 2030 45-863a95 95 0 0 0-111-98l-859 151 116-320a65 65 0 0 0-20-73l-941-762 212-99a65 65 0 0 0 34-79l-186-572 542 115a65 65 0 0 0 73-38l105-247 423 454a65 65 0 0 0 111-57l-204-1052 327 189a65 65 0 0 0 91-27l332-652 332 652a65 65 0 0 0 91 27l327-189-204 1052a65 65 0 0 0 111 57l423-454 105 247a65 65 0 0 0 73 38l542-115-186 572a65 65 0 0 0 34 79l212 99-941 762a65 65 0 0 0-20 73l116 320-859-151a95 95 0 0 0-111 98l45 863z" />
    </svg>
  );
}

export default async function LangPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  const l = pickLang(lang);
  const t = STRINGS[l];
  const other = l === "en" ? "fr" : "en";
  const cal = loadCalibration();
  const auc = cal.generic_ge_30.cv_auc_mean.toFixed(2);
  const calN = cal.n_trees.toLocaleString("en-US");

  return (
    <div className="wrap">
      <header className="topbar">
        <a className="brand" href={`/${l}`}>
          <MapleLeaf />
          <span>
            <span className="eyebrow">{t.eyebrow}</span>
            <br />
            <span className="brandname">{t.siteName}</span>
          </span>
        </a>
        <Link className="langtoggle" href={`/${other}`}>
          {t.switchLang}
        </Link>
      </header>

      <main>
        <section className="hero">
          <h1 className="display">{t.siteName}</h1>
          <p className="tagline">{t.tagline}</p>
          <Explorer lang={l} />
        </section>

        <section className="methodsec">
          <p className="kicker">{t.method.kicker}</p>
          <h2 className="display">{t.method.title}</h2>
          <div className="steps">
            <div className="step">
              <div className="num">01</div>
              <h3>{t.method.step1t}</h3>
              <p>{t.method.step1b}</p>
            </div>
            <div className="step">
              <div className="num">02</div>
              <h3>{t.method.step2t}</h3>
              <p>{t.method.step2b}</p>
            </div>
            <div className="step">
              <div className="num">03</div>
              <h3>{t.method.step3t}</h3>
              <p>{t.method.step3b}</p>
            </div>
          </div>
          <div className="accbox">
            <h3>{t.method.accuracyTitle}</h3>
            <p>{t.method.accuracyBody(auc, calN)}</p>
          </div>
        </section>

        <section className="downloadsec">
          <p className="kicker">{t.download.kicker}</p>
          <h2 className="display">{t.download.title}</h2>
          <p>{t.download.body}</p>
          <DownloadPicker
            wardLabel={t.download.wardLabel}
            geojsonLabel={t.download.geojson}
            csvLabel={t.download.csv}
          />
        </section>

        <McpConnect lang={l} />
      </main>

      <footer className="footer">
        <div className="footer-inner">
          <p className="footer-wordmark">{t.footer.wordmark}</p>
          <p>{t.footer.tagline}</p>
          <p>{t.footer.dataNote}</p>
          <p>
            <a href="https://x.com/richardsondx">X</a> ·{" "}
            <a href="https://github.com/richardsondx">GitHub</a>
          </p>
        </div>
      </footer>
    </div>
  );
}
