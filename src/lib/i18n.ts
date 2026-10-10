// EN/FR strings for Toronto Tree Canopy.
// Copy rules: no em dashes anywhere; every line carries a number, a mechanism,
// or a reason; proper nouns get their gloss on first use.

export type Lang = "en" | "fr";

export const LANGS: Lang[] = ["en", "fr"];

export function pickLang(v: string | null | undefined): Lang {
  return v === "fr" ? "fr" : "en";
}

const en = {
  siteName: "Toronto Tree Canopy",
  eyebrow: "Open Nshipyard",
  tagline:
    "Type a Toronto address. Get a per-lot tree screening: how many crowns the detector found, the probability any clears the 30 cm permit threshold, canopy percent, and what to do next.",
  addressPlaceholder: "e.g. 407 Arlington Ave, Toronto",
  searchButton: "Screen this lot",
  searching: "Screening…",
  switchLang: "Français",
  exampleAddresses: "Try:",
  heroStats:
    "Ward 12 (Davenport) pilot · crowns detected from City of Toronto 2022 orthorectified aerial imagery · screening signal, not a permit determination",

  suggestLabel: "Address suggestions",

  screen: {
    lotLabel: "Lot",
    parcelId: "Parcel",
    imageryVintage: "Imagery vintage",
    crownsDetected: "Crowns detected",
    canopyCover: "Canopy cover",
    pAnyMature: "Chance any crown clears 30 cm",
    pAnyDistinctive: "Chance any crown clears 61 cm",
    neighbourTitle: "Neighbouring crowns (within 6 m of the boundary)",
    neighbourWhy:
      "The by-law site plan must show all trees 30 cm and up on adjacent properties within 6 m of the boundary, so the screen counts crowns across that line too.",
    crownListTitle: "Detected crowns",
    crownLabel: (i: number) => `Crown ${i}`,
    crownDiameter: "Crown diameter",
    dbhEstimate: "Estimated trunk diameter (DBH)",
    pi95: "95% prediction interval",
    pGe30: "Chance trunk is 30 cm or more",
    pGt61: "Chance trunk is over 61 cm (Distinctive tier)",
    likelyMature: "likely mature",
    maybeMature: "possible",
    young: "young",
    honesty:
      "Screening signal only; not a permit determination. The City's Private Tree By-law (Municipal Code Chapter 813, Article III) requires a permit before injuring or removing any private tree 30 cm or more in trunk diameter, measured at 1.4 m; the September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Only a certified arborist can confirm trunk diameter on site.",
    vintageCaveat:
      "Imagery is from 2022. Trees removed after that are invisible to this screen, and new growth since then is missing too.",
    sampleBanner:
      "Sample data. These parcels are synthetic placeholders so the app can run; the Ward 12 pilot will replace them with measured detections.",
    methodLine: (f1: string) => `Detection F1 ${f1}, measured on hand-labeled pilot tiles (pilot number pending).`,
    sampleMethod:
      "Detection F1 shown is a sample placeholder; the pilot has not measured its own accuracy yet.",
    feeLine: (n: number, total: string) =>
      `If an arborist confirms ${n} ${n === 1 ? "tree" : "trees"} for removal, the 2026 construction-related permit fee is $436.39 per tree, for ${total}.`,
    nextStep: "Get an arborist report before planning around these crowns.",
    outsidePilot:
      "This address falls outside the Ward 12 (Davenport) pilot area. The screen covers the pilot parcels only.",
    notFound: "Address not found in the City's Address Points.",
    lookupError: "The screening request failed. Check the address and try again.",
    noScreenYet: "Screen a pilot address to see the per-lot crown map and verdict.",
  },

  verdict: {
    noCrowns: (nb: number) =>
      `No crowns detected on this lot in 2022 imagery.${nb > 0 ? ` The screen found ${nb} ${nb === 1 ? "crown" : "crowns"} on neighbouring parcels within 6 m of the boundary; the by-law site plan must show trees 30 cm and up there too.` : ""}`,
    withCrowns: (n: number, canopy: string, p30: string, p61: string, nb: number) =>
      `${n} ${n === 1 ? "crown" : "crowns"} detected on this lot in 2022 imagery, covering ${canopy} of the parcel. Chance at least one clears the 30 cm permit threshold: ${p30}. Chance at least one clears the 61 cm Distinctive tier: ${p61}.${nb > 0 ? ` The 6 m neighbour buffer holds ${nb} more ${nb === 1 ? "crown" : "crowns"}.` : ""} Treat this as a screening signal, then get an arborist before planning around them.`,
  },

  map: {
    title: "Crown map",
    legendMature: "crown likely 30 cm or more (probability at least 50%)",
    legendPossible: "crown possible",
    legendParcel: "parcel boundary",
    legendBuffer: "6 m neighbour buffer",
    scaleBar: (m: number) => `${m} m`,
    missingImage:
      "The aerial map image for this parcel is not rendered yet. Renders are produced when the parcel dataset ships, so this appears after the next pipeline run.",
  },

  download: {
    kicker: "Open data",
    title: "Download the pilot dataset",
    body: "Every parcel in the pilot with its detected crowns, estimated trunk diameters with 95% prediction intervals, and permit-threshold probabilities. MIT licence for the code; data carries the City of Toronto open data terms.",
    geojson: "Download GeoJSON",
    csv: "Download CSV",
  },

  method: {
    kicker: "How the screen works",
    title: "From 2022 aerial imagery to a per-lot verdict",
    step1t: "Detect crowns",
    step1b:
      "A DeepForest detection model (RetinaNet with pre-trained weights, MIT licence) draws crown polygons on the City of Toronto's 2022 orthorectified aerial imagery, 8 cm resolution. Instance delineation is the hard part, so per-tree counts carry a stated error bar.",
    step2t: "Estimate trunk diameter",
    step2b:
      "Crown diameter is converted to trunk diameter (DBH, measured at 1.4 m) with allometry fit on Toronto's 688,335 street-tree records, species by species, urban trees only. The model never guesses species from colour; every estimate reports a 95% prediction interval.",
    step3t: "Score against the by-law",
    step3b:
      "Each crown gets the probability its trunk clears the 30 cm permit threshold of the Private Tree By-law (Municipal Code Chapter 813, Article III) and the 61 cm Distinctive tier added in September 2026. Crowns are also rolled up over the 6 m neighbour buffer, matching the by-law's site-plan rule.",
    accuracyTitle: "Accuracy (pilot will measure)",
    accuracyBody:
      "The pilot measures detection F1 against hand-labeled tiles and calibration R2 against held-out street trees. Until the pipeline reports its own numbers, the screen carries sample placeholders, marked as such.",
  },

  mcp: {
    kicker: "For AI agents",
    title: "Connect your agent",
    body: "The screen is available over MCP (Streamable HTTP) and a plain REST API. Two tools: canopy_screen takes an address and returns the full screening payload; parcel_crowns takes a parcel ID and returns its crowns. Paste the block into your harness and point it at this server.",
    tabs: { chatgpt: "ChatGPT", claude: "Claude", claudecode: "Claude Code", cli: "CLI", other: "Other" },
    cardTitle: "Paste into {tab}",
    otherTitle: "Connect any MCP client",
    copy: "Copy",
    copied: "Copied",
    chatgptNote: "ChatGPT needs the MCP server added as a custom tool under Developer mode.",
    otherBody: "Any MCP client that speaks Streamable HTTP JSON-RPC 2.0 can call this server.",
    mcpEndpoint: "MCP endpoint",
    openapiSpec: "OpenAPI spec",
    restExample: "REST example",
    pChatgpt:
      "Add this MCP server in ChatGPT (Developer mode > Tools > Add MCP server):\n\nServer URL: {origin}/mcp\nName: {displayName}\n\nThen ask: \"Screen {displayName} for 407 Arlington Ave\" or use canopy_screen with any Toronto address in the Ward 12 pilot.",
    pClaude:
      "Connect this MCP server in Claude (Settings > Integrations > Add):\n\nServer URL: {origin}/mcp\nName: {displayName}\n\nThen ask it to screen a Ward 12 address with canopy_screen, e.g. 407 Arlington Ave.",
    pClaudeCode:
      "Claude Code connects to this MCP server with one command:\n\nclaude mcp add --transport http {slug} {origin}/mcp\n\nThen: \"Use canopy_screen to screen 407 Arlington Ave\" or parcel_crowns with a parcel ID like TOP-W12-0103.",
    pCli:
      "Any JSON-RPC 2.0 client over Streamable HTTP works:\n\ncurl -s -X POST {origin}/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"canopy_screen\",\"arguments\":{\"address\":\"407 Arlington Ave\"}}}'",
  },

  footer: {
    wordmark: "Open Nshipyard",
    tagline: "Civic data tools, open source, built in Toronto.",
    dataNote: "Screening from City of Toronto open data: Address Points, 2022 orthorectified imagery, street-tree inventory. Not legal or arboricultural advice.",
  },
};

const fr = {
  siteName: "Canopée des arbres de Toronto",
  eyebrow: "Open Nshipyard",
  tagline:
    "Entrez une adresse de Toronto. Obtenez un dépistage par lot : le nombre de couronnes détectées, la probabilité qu'une d'elles atteigne le seuil de 30 cm, le pourcentage de couvert et les prochaines étapes.",
  addressPlaceholder: "p. ex. 407 Arlington Ave, Toronto",
  searchButton: "Dépister ce lot",
  searching: "Dépistage…",
  switchLang: "English",
  exampleAddresses: "Essayez :",
  heroStats:
    "Projet pilote du quartier 12 (Davenport) · couronnes détectées à partir des images aériennes orthorectifiées de 2022 de la Ville de Toronto · signal de dépistage, pas une décision de permis",

  suggestLabel: "Suggestions d'adresses",

  screen: {
    lotLabel: "Lot",
    parcelId: "Parcelle",
    imageryVintage: "Millésime des images",
    crownsDetected: "Couronnes détectées",
    canopyCover: "Couvert de canopée",
    pAnyMature: "Probabilité qu'une couronne atteigne 30 cm",
    pAnyDistinctive: "Probabilité qu'une couronne dépasse 61 cm",
    neighbourTitle: "Couronnes voisines (à moins de 6 m de la limite)",
    neighbourWhy:
      "Le plan de situation exigé par le règlement doit montrer tous les arbres de 30 cm et plus sur les propriétés adjacentes à moins de 6 m de la limite; le dépistage compte donc aussi les couronnes de l'autre côté de cette ligne.",
    crownListTitle: "Couronnes détectées",
    crownLabel: (i: number) => `Couronne ${i}`,
    crownDiameter: "Diamètre de la couronne",
    dbhEstimate: "Diamètre du tronc estimé (DHP)",
    pi95: "Intervalle de prédiction à 95 %",
    pGe30: "Probabilité que le tronc atteigne 30 cm ou plus",
    pGt61: "Probabilité que le tronc dépasse 61 cm (catégorie Distinctive)",
    likelyMature: "probablement mature",
    maybeMature: "possible",
    young: "jeune",
    honesty:
      "Signal de dépistage seulement; ce n'est pas une décision de permis. Le règlement sur les arbres privés de la Ville (chapitre 813 du Code municipal, article III) exige un permis avant d'endommager ou d'abattre tout arbre privé de 30 cm ou plus de diamètre, mesuré à 1,4 m; les modifications de septembre 2026 ont ajouté une catégorie Distinctive au-delà de 61 cm avec des protections renforcées. Seul un arboriste certifié peut confirmer le diamètre du tronc sur place.",
    vintageCaveat:
      "Les images datent de 2022. Les arbres abattus depuis sont invisibles à ce dépistage, et la croissance récente y manque aussi.",
    sampleBanner:
      "Données d'exemple. Ces parcelles sont des substituts synthétiques pour faire fonctionner l'application; le projet pilote du quartier 12 les remplacera par des détections mesurées.",
    methodLine: (f1: string) => `F1 de détection ${f1}, mesuré sur des tuiles étiquetées à la main du projet pilote (chiffre du pilote à venir).`,
    sampleMethod:
      "Le F1 de détection affiché est une valeur d'exemple; le pilote n'a pas encore mesuré sa propre précision.",
    feeLine: (n: number, total: string) =>
      `Si un arboriste confirme ${n} ${n === 1 ? "arbre" : "arbres"} à abattre, les frais de permis 2026 pour travaux de construction sont de 436,39 $ par arbre, soit ${total}.`,
    nextStep: "Obtenez un rapport d'arboriste avant de planifier autour de ces couronnes.",
    outsidePilot:
      "Cette adresse se situe hors de la zone du projet pilote du quartier 12 (Davenport). Le dépistage ne couvre que les parcelles du pilote.",
    notFound: "Adresse introuvable dans les points d'adresse de la Ville.",
    lookupError: "La demande de dépistage a échoué. Vérifiez l'adresse et réessayez.",
    noScreenYet: "Dépistez une adresse du pilote pour voir la carte des couronnes et le verdict du lot.",
  },

  verdict: {
    noCrowns: (nb: number) =>
      `Aucune couronne détectée sur ce lot dans les images de 2022.${nb > 0 ? ` Le dépistage a trouvé ${nb} ${nb === 1 ? "couronne" : "couronnes"} sur les parcelles voisines à moins de 6 m de la limite; le plan de situation exigé par le règlement doit aussi montrer les arbres de 30 cm et plus à cet endroit.` : ""}`,
    withCrowns: (n: number, canopy: string, p30: string, p61: string, nb: number) =>
      `${n} ${n === 1 ? "couronne détectée" : "couronnes détectées"} sur ce lot dans les images de 2022, couvrant ${canopy} de la parcelle. Probabilité qu'au moins une atteigne le seuil de permis de 30 cm : ${p30}. Probabilité qu'au moins une dépasse la catégorie Distinctive de 61 cm : ${p61}.${nb > 0 ? ` La zone tampon de 6 m contient ${nb} ${nb === 1 ? "couronne" : "couronnes"} de plus.` : ""} Considérez ceci comme un signal de dépistage, puis obtenez un rapport d'arboriste avant de planifier autour d'elles.`,
  },

  map: {
    title: "Carte des couronnes",
    legendMature: "couronne probablement de 30 cm ou plus (probabilité d'au moins 50 %)",
    legendPossible: "couronne possible",
    legendParcel: "limite de la parcelle",
    legendBuffer: "zone tampon de 6 m",
    scaleBar: (m: number) => `${m} m`,
    missingImage:
      "La carte aérienne de cette parcelle n'est pas encore produite. Les rendus sont générés à chaque publication du jeu de données, donc elle apparaîtra après la prochaine exécution du pipeline.",
  },

  download: {
    kicker: "Données ouvertes",
    title: "Télécharger le jeu de données pilote",
    body: "Chaque parcelle du pilote avec ses couronnes détectées, les diamètres de tronc estimés avec intervalles de prédiction à 95 % et les probabilités liées aux seuils de permis. Code sous licence MIT; les données suivent les conditions des données ouvertes de la Ville de Toronto.",
    geojson: "Télécharger GeoJSON",
    csv: "Télécharger CSV",
  },

  method: {
    kicker: "Fonctionnement du dépistage",
    title: "Des images aériennes de 2022 au verdict par lot",
    step1t: "Détecter les couronnes",
    step1b:
      "Un modèle de détection DeepForest (RetinaNet avec poids pré-entraînés, licence MIT) trace les polygones de couronnes sur les images aériennes orthorectifiées de 2022 de la Ville de Toronto, à 8 cm de résolution. La délimitation des instances est la partie difficile, donc les décomptes par arbre portent une marge d'erreur déclarée.",
    step2t: "Estimer le diamètre du tronc",
    step2b:
      "Le diamètre de la couronne est converti en diamètre du tronc (DHP, mesuré à 1,4 m) avec une allométrie ajustée sur les 688 335 arbres de rue de Toronto, espèce par espèce, arbres urbains seulement. Le modèle ne devine jamais l'espèce à partir de la couleur; chaque estimation présente un intervalle de prédiction à 95 %.",
    step3t: "Évaluer selon le règlement",
    step3b:
      "Chaque couronne reçoit la probabilité que son tronc atteigne le seuil de permis de 30 cm du règlement sur les arbres privés (chapitre 813 du Code municipal, article III) et la catégorie Distinctive de 61 cm ajoutée en septembre 2026. Les couronnes sont aussi cumulées sur la zone tampon de 6 m des voisins, comme l'exige la règle du plan de situation.",
    accuracyTitle: "Précision (le pilote la mesurera)",
    accuracyBody:
      "Le pilote mesure le F1 de détection sur des tuiles étiquetées à la main et le R2 d'étalonnage sur des arbres de rue exclus de l'ajustement. En attendant les chiffres du pipeline, le dépistage porte des valeurs d'exemple, signalées comme telles.",
  },

  mcp: {
    kicker: "Pour les agents IA",
    title: "Connectez votre agent",
    body: "Le dépistage est offert en MCP (HTTP diffusable) et en API REST simple. Deux outils : canopy_screen prend une adresse et renvoie le dépistage complet; parcel_crowns prend un identifiant de parcelle et renvoie ses couronnes. Collez le bloc dans votre harnais et pointez-le vers ce serveur.",
    tabs: { chatgpt: "ChatGPT", claude: "Claude", claudecode: "Claude Code", cli: "CLI", other: "Autre" },
    cardTitle: "Coller dans {tab}",
    otherTitle: "Connecter tout client MCP",
    copy: "Copier",
    copied: "Copié",
    chatgptNote: "ChatGPT exige l'ajout du serveur MCP comme outil personnalisé en mode Développeur.",
    otherBody: "Tout client MCP parlant JSON-RPC 2.0 sur HTTP diffusable peut appeler ce serveur.",
    mcpEndpoint: "Point d'accès MCP",
    openapiSpec: "Spécification OpenAPI",
    restExample: "Exemple REST",
    pChatgpt:
      "Ajoutez ce serveur MCP dans ChatGPT (mode Développeur > Outils > Ajouter un serveur MCP) :\n\nURL du serveur : {origin}/mcp\nNom : {displayName}\n\nPuis demandez : « Dépiste {displayName} pour 407 Arlington Ave » ou utilisez canopy_screen avec toute adresse torontoise du pilote du quartier 12.",
    pClaude:
      "Connectez ce serveur MCP dans Claude (Paramètres > Intégrations > Ajouter) :\n\nURL du serveur : {origin}/mcp\nNom : {displayName}\n\nPuis demandez-lui de dépister une adresse du quartier 12 avec canopy_screen, p. ex. 407 Arlington Ave.",
    pClaudeCode:
      "Claude Code se connecte à ce serveur MCP en une commande :\n\nclaude mcp add --transport http {slug} {origin}/mcp\n\nPuis : « Utilise canopy_screen pour dépister 407 Arlington Ave » ou parcel_crowns avec un identifiant de parcelle comme TOP-W12-0103.",
    pCli:
      "Tout client JSON-RPC 2.0 sur HTTP diffusable fonctionne :\n\ncurl -s -X POST {origin}/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"canopy_screen\",\"arguments\":{\"address\":\"407 Arlington Ave\"}}}'",
  },

  footer: {
    wordmark: "Open Nshipyard",
    tagline: "Outils de données civiques, open source, construits à Toronto.",
    dataNote: "Dépistage à partir des données ouvertes de la Ville de Toronto : points d'adresse, images de 2022 orthorectifiées, inventaire des arbres de rue. Ni conseil juridique ni conseil arboricole.",
  },
};

export const STRINGS = { en, fr };
export type Strings = typeof en;
