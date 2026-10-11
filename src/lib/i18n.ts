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
    "Type a Toronto address. Get a per-lot tree screening from 2023 LiDAR: tall-canopy area, tallest surface, canopy percent, and the calibrated chance a mature tree stands on the lot.",
  addressPlaceholder: "e.g. 1843 Eglinton Ave W, Toronto",
  searchButton: "Screen this lot",
  searching: "Screening…",
  switchLang: "Français",
  exampleAddresses: "Try:",
  heroStats:
    "498,463 Toronto parcels · tall-canopy structure measured from 2023 airborne LiDAR (1 m), buildings masked · mature-tree probability calibrated on 9,811 street trees · screening signal, not a permit determination",

  suggestLabel: "Address suggestions",

  screen: {
    lotLabel: "Lot",
    parcelId: "Parcel",
    imageryVintage: "Canopy vintage",
    tallCanopyArea: "Tall canopy (8 m and up)",
    maxHeight: "Tallest surface",
    canopyCover: "Tall-canopy cover",
    pAnyMature: "Chance of a mature tree (30 cm+)",
    pAnyDistinctive: "Chance of a Distinctive tree (61 cm+)",
    neighbourTitle: "Neighbouring tall canopy (within 6 m of the boundary)",
    neighbourWhy:
      "The by-law site plan must show all trees 30 cm and up on adjacent properties within 6 m of the boundary, so the screen measures the 6 m band around the lot too.",
    honesty:
      "Screening signal only; not a permit determination. The tall-canopy numbers measure elevated surface 6 m and up from 2023 LiDAR. City building footprints (2 m buffer) are masked out of the LiDAR surface before measurement, so rooftops no longer read as canopy, but other tall structures (sheds, gazebos, retaining walls) still can. The mature-tree chance is a statistical calibration fit on the City's street-tree inventory (managed road-allowance trees, pruned and spaced by the City), applied to tree-like LiDAR peaks on the lot; peaks smoother than 95% of measured street-tree crowns are treated as roofs and excluded. The City's Private Tree By-law (Municipal Code Chapter 813, Article III) requires a permit before injuring or removing any private tree 30 cm or more in trunk diameter, measured at 1.4 m; the September 2026 amendments added a Distinctive tier above 61 cm with stronger protections. Only a certified arborist can confirm trunk diameter on site.",
    vintageCaveat:
      "Canopy structure is from 2023 LiDAR. Trees removed after that are invisible to this screen, and growth since then is missing too.",
    methodLine: (auc: string, n: string) =>
      `Mature-tree calibration AUC ${auc}, fit on ${n} Ward 12 street trees with known trunk diameters against their LiDAR height and canopy area.`,
    nextStep: "Get an arborist report before planning around these numbers.",
    outsideToronto:
      "This address falls outside Toronto. The screen covers Toronto parcels only.",
    noParcelData:
      "No canopy data for this location. The address is inside Toronto but matches no parcel in the dataset.",
    notFound: "Address not found in the City's Address Points.",
    lookupError: "The screening request failed. Check the address and try again.",
    noScreenYet: "Screen a Toronto address to see the lot's tall-canopy measurements and verdict.",
  },

  verdict: {
    noTallCanopy: (p30: string, bufArea: string, bufP30: string) =>
      `2023 LiDAR found no surface 8 m or taller on this lot. The calibrated chance a mature tree (trunk 30 cm or more) stands on the lot is ${p30}.${bufArea !== "0" && bufArea !== "0.0" ? ` The 6 m neighbour band holds ${bufArea} m² of tall canopy with a ${bufP30} mature-tree chance; the by-law site plan must show trees 30 cm and up there too.` : ""} Treat this as a screening signal, then get an arborist before planning around it.`,
    withCanopy: (
      area8: string,
      pct8: string,
      maxH: string,
      p30: string,
      p61: string,
      bufArea: string,
      bufP30: string,
      lotPeaks: number,
    ) =>
      `2023 LiDAR measured ${area8} m² of surface 8 m or taller on this lot (${pct8}% of the parcel), peaking at ${maxH} m. Calibrated on the street-tree inventory, the chance at least one mature tree (trunk 30 cm or more) stands on the lot is ${p30}; the chance of a Distinctive tree (over 61 cm) is ${p61}.${lotPeaks === 0 ? " No tree-like LiDAR peaks 6 m or taller were found on the lot itself." : ""}${bufArea !== "0" && bufArea !== "0.0" ? ` The 6 m neighbour band holds ${bufArea} m² of tall canopy with a ${bufP30} mature-tree chance; the by-law site plan must show trees 30 cm and up there too.` : ""} This is a screening signal from LiDAR structure, not a count of individual crowns; get an arborist before planning around it.`,
  },

  map: {
    title: "Tall-canopy map",
    legendTall: "tall canopy (8 m and up, 2023 LiDAR)",
    legendParcel: "parcel boundary",
    legendBuffer: "6 m neighbour buffer",
    scaleBar: (m: number) => `${m} m`,
    missingImage:
      "The canopy map for this parcel could not be rendered. The map is drawn on demand from the 2023 LiDAR surface; try again in a moment.",
  },

  download: {
    kicker: "Open data",
    title: "Download the Toronto canopy dataset, by ward",
    body: "Every Toronto parcel with its measured 2023 LiDAR tall-canopy metrics (area at the 6 m and 8 m thresholds, max height, canopy percent) and calibrated mature-tree probabilities, for the lot and the 6 m neighbour buffer. Pick a ward and a format below. MIT licence for the code; data carries the City of Toronto and NRCan open data terms.",
    wardLabel: "Ward",
    geojson: "Download GeoJSON",
    csv: "Download CSV",
  },

  method: {
    kicker: "How the screen works",
    title: "From 2023 LiDAR to a per-lot verdict",
    step1t: "Measure canopy structure",
    step1b:
      "The NRCan HRDEM mosaic (CanElevation series, open data) serves 2023 airborne LiDAR flown for the Toronto and Region Conservation Authority over Toronto at 1 m. Surface minus terrain gives a canopy height model; City building footprints are masked out with a 2 m buffer before measurement. Per parcel the screen reports tall-canopy area at 6 m and 8 m, max height, and canopy percent, for the lot and for the 6 m neighbour band the by-law's site-plan rule cares about.",
    step2t: "Calibrate mature-tree probability",
    step2b:
      "A logistic regression maps LiDAR height and canopy area around 9,811 Ward 12 street trees to the probability the trunk clears 30 cm (and 61 cm for the Distinctive tier). Street trees are managed road-allowance trees, so the transfer to private trees is approximate; the fit quality is reported as AUC below.",
    step3t: "Score against the by-law",
    step3b:
      "LiDAR peaks 6 m and up on the lot are scored with the calibration and rolled up to the chance at least one mature tree stands on the lot, and the same for the 6 m neighbour band. Buildings are masked out of the surface first, so the number is a screening signal, never a permit determination.",
    accuracyTitle: "Accuracy (measured)",
    accuracyBody: (auc: string, n: string) =>
      `The mature-tree calibration scores AUC ${auc} on ${n} Ward 12 street trees with known trunk diameters (5-fold cross-validation). Individual crown detection was tried first and failed honestly: pre-trained DeepForest F1 0.023, fine-tuned F1 0.000, and 1 m watershed F1 0.046 on hand-labeled tiles, because all five City orthophoto vintages are leaf-off spring captures. This screen sidesteps detection entirely: it measures canopy structure, not crowns.`,
  },

  mcp: {
    kicker: "For AI agents",
    title: "Connect your agent",
    body: "The screen is available over MCP (Streamable HTTP) and a plain REST API. Two tools: canopy_screen takes an address and returns the full screening payload; parcel_crowns takes a parcel ID and returns its parcel payload (the crowns array is reserved for a future segmentation win and currently empty). Paste the block into your harness and point it at this server.",
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
      "Add this MCP server in ChatGPT (Developer mode > Tools > Add MCP server):\n\nServer URL: {origin}/mcp\nName: {displayName}\n\nThen ask: \"Screen {displayName} for 1843 Eglinton Ave W\" or use canopy_screen with any Toronto address.",
    pClaude:
      "Connect this MCP server in Claude (Settings > Integrations > Add):\n\nServer URL: {origin}/mcp\nName: {displayName}\n\nThen ask it to screen a Toronto address with canopy_screen, e.g. 1843 Eglinton Ave W.",
    pClaudeCode:
      "Claude Code connects to this MCP server with one command:\n\nclaude mcp add --transport http {slug} {origin}/mcp\n\nThen: \"Use canopy_screen to screen 1843 Eglinton Ave W\" or parcel_crowns with a parcel ID like TOP-5293472.",
    pCli:
      "Any JSON-RPC 2.0 client over Streamable HTTP works:\n\ncurl -s -X POST {origin}/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"canopy_screen\",\"arguments\":{\"address\":\"1843 Eglinton Ave W\"}}}'",
  },

  footer: {
    wordmark: "Open Nshipyard",
    tagline: "Civic data tools, open source, built in Toronto.",
    dataNote: "Screening from open data: 2023 airborne LiDAR via the NRCan HRDEM mosaic, City of Toronto Address Points and street-tree inventory. Not legal or arboricultural advice.",
  },
};

const fr = {
  siteName: "Canopée des arbres de Toronto",
  eyebrow: "Open Nshipyard",
  tagline:
    "Entrez une adresse de Toronto. Obtenez un dépistage par lot à partir du LiDAR de 2023 : superficie de canopée haute, surface la plus haute, pourcentage de couvert et probabilité calibrée qu'un arbre mature s'y trouve.",
  addressPlaceholder: "p. ex. 1843 Eglinton Ave W, Toronto",
  searchButton: "Dépister ce lot",
  searching: "Dépistage…",
  switchLang: "English",
  exampleAddresses: "Essayez :",
  heroStats:
    "498 463 parcelles de Toronto · structure de la canopée haute mesurée par LiDAR aéroporté de 2023 (1 m), bâtiments masqués · probabilité d'arbre mature calibrée sur 9 811 arbres de rue · signal de dépistage, pas une décision de permis",

  suggestLabel: "Suggestions d'adresses",

  screen: {
    lotLabel: "Lot",
    parcelId: "Parcelle",
    imageryVintage: "Millésime de la canopée",
    tallCanopyArea: "Canopée haute (8 m et plus)",
    maxHeight: "Surface la plus haute",
    canopyCover: "Couvert de canopée haute",
    pAnyMature: "Probabilité d'un arbre mature (30 cm+)",
    pAnyDistinctive: "Probabilité d'un arbre Distinctive (61 cm+)",
    neighbourTitle: "Canopée haute voisine (à moins de 6 m de la limite)",
    neighbourWhy:
      "Le plan de situation exigé par le règlement doit montrer tous les arbres de 30 cm et plus sur les propriétés adjacentes à moins de 6 m de la limite; le dépistage mesure donc aussi la bande de 6 m autour du lot.",
    honesty:
      "Signal de dépistage seulement; ce n'est pas une décision de permis. Les chiffres de canopée haute mesurent la surface élevée à 6 m et plus d'après le LiDAR de 2023. Les emprises des bâtiments de la Ville (zone tampon de 2 m) sont masquées de la surface LiDAR avant la mesure, donc les toits ne se lisent plus comme de la canopée, mais d'autres structures hautes (remises, gloriettes, murs de soutènement) le peuvent encore. La probabilité d'arbre mature est un calibrage statistique ajusté sur l'inventaire des arbres de rue de la Ville (arbres d'emprise gérés, taillés et espacés par la Ville), appliqué aux pics LiDAR d'allure arborée du lot; les pics plus lisses que 95 % des couronnes d'arbres de rue mesurées sont traités comme des toits et exclus. Le règlement sur les arbres privés de la Ville (chapitre 813 du Code municipal, article III) exige un permis avant d'endommager ou d'abattre tout arbre privé de 30 cm ou plus de diamètre, mesuré à 1,4 m; les modifications de septembre 2026 ont ajouté une catégorie Distinctive au-delà de 61 cm avec des protections renforcées. Seul un arboriste certifié peut confirmer le diamètre du tronc sur place.",
    vintageCaveat:
      "La structure de la canopée date du LiDAR de 2023. Les arbres abattus depuis sont invisibles à ce dépistage, et la croissance récente y manque aussi.",
    methodLine: (auc: string, n: string) =>
      `AUC de calibrage des arbres matures : ${auc}, ajustée sur ${n} arbres de rue du quartier 12 au diamètre connu, selon leur hauteur LiDAR et leur superficie de canopée.`,
    nextStep: "Obtenez un rapport d'arboriste avant de planifier autour de ces chiffres.",
    outsideToronto:
      "Cette adresse se situe hors de Toronto. Le dépistage ne couvre que les parcelles de Toronto.",
    noParcelData:
      "Aucune donnée de canopée pour cet endroit. L'adresse est à Toronto mais ne correspond à aucune parcelle du jeu de données.",
    notFound: "Adresse introuvable dans les points d'adresse de la Ville.",
    lookupError: "La demande de dépistage a échoué. Vérifiez l'adresse et réessayez.",
    noScreenYet: "Dépistez une adresse de Toronto pour voir les mesures de canopée haute et le verdict du lot.",
  },

  verdict: {
    noTallCanopy: (p30: string, bufArea: string, bufP30: string) =>
      `Le LiDAR de 2023 n'a trouvé aucune surface de 8 m ou plus sur ce lot. La probabilité calibrée qu'un arbre mature (tronc de 30 cm ou plus) s'y trouve est de ${p30}.${bufArea !== "0" && bufArea !== "0.0" ? ` La bande voisine de 6 m contient ${bufArea} m² de canopée haute avec une probabilité d'arbre mature de ${bufP30}; le plan de situation exigé par le règlement doit aussi montrer les arbres de 30 cm et plus à cet endroit.` : ""} Considérez ceci comme un signal de dépistage, puis obtenez un rapport d'arboriste avant de planifier autour de ce lot.`,
    withCanopy: (
      area8: string,
      pct8: string,
      maxH: string,
      p30: string,
      p61: string,
      bufArea: string,
      bufP30: string,
      lotPeaks: number,
    ) =>
      `Le LiDAR de 2023 a mesuré ${area8} m² de surface de 8 m ou plus sur ce lot (${pct8} % de la parcelle), culminant à ${maxH} m. Selon le calibrage sur l'inventaire des arbres de rue, la probabilité qu'au moins un arbre mature (tronc de 30 cm ou plus) s'y trouve est de ${p30}; celle d'un arbre Distinctive (plus de 61 cm) est de ${p61}.${lotPeaks === 0 ? " Aucun pic LiDAR d'allure arborée de 6 m ou plus n'a été trouvé sur le lot lui-même." : ""}${bufArea !== "0" && bufArea !== "0.0" ? ` La bande voisine de 6 m contient ${bufArea} m² de canopée haute avec une probabilité d'arbre mature de ${bufP30}; le plan de situation exigé par le règlement doit aussi montrer les arbres de 30 cm et plus à cet endroit.` : ""} Ceci est un signal de dépistage tiré de la structure LiDAR, pas un décompte de couronnes individuelles; obtenez un rapport d'arboriste avant de planifier autour de ce lot.`,
  },

  map: {
    title: "Carte de la canopée haute",
    legendTall: "canopée haute (8 m et plus, LiDAR 2023)",
    legendParcel: "limite de la parcelle",
    legendBuffer: "zone tampon de 6 m",
    scaleBar: (m: number) => `${m} m`,
    missingImage:
      "La carte de canopée de cette parcelle n'a pas pu être produite. La carte est dessinée à la demande à partir de la surface LiDAR de 2023; réessayez dans un moment.",
  },

  download: {
    kicker: "Données ouvertes",
    title: "Télécharger le jeu de données de canopée de Toronto, par quartier",
    body: "Chaque parcelle de Toronto avec ses mesures de canopée haute du LiDAR de 2023 (superficie aux seuils de 6 m et 8 m, hauteur maximale, pourcentage de couvert) et ses probabilités calibrées d'arbre mature, pour le lot et la zone tampon de 6 m. Choisissez un quartier et un format ci-dessous. Code sous licence MIT; les données suivent les conditions des données ouvertes de la Ville de Toronto et de RNCan.",
    wardLabel: "Quartier",
    geojson: "Télécharger GeoJSON",
    csv: "Télécharger CSV",
  },

  method: {
    kicker: "Fonctionnement du dépistage",
    title: "Du LiDAR de 2023 au verdict par lot",
    step1t: "Mesurer la structure de la canopée",
    step1b:
      "La mosaïque HRDEM de RNCan (série CanÉlévation, données ouvertes) diffuse le LiDAR aéroporté de 2023 capté pour l'Office de protection de la nature de Toronto et de la région, à 1 m. La surface moins le terrain donne un modèle de hauteur de canopée; les emprises des bâtiments de la Ville sont masquées avec une zone tampon de 2 m avant la mesure. Par parcelle, le dépistage indique la superficie de canopée haute à 6 m et 8 m, la hauteur maximale et le pourcentage de couvert, pour le lot et pour la bande voisine de 6 m visée par la règle du plan de situation.",
    step2t: "Calibrer la probabilité d'arbre mature",
    step2b:
      "Une régression logistique relie la hauteur LiDAR et la superficie de canopée autour de 9 811 arbres de rue du quartier 12 à la probabilité que le tronc atteigne 30 cm (et 61 cm pour la catégorie Distinctive). Les arbres de rue sont des arbres d'emprise gérés, donc le transfert aux arbres privés est approximatif; la qualité de l'ajustement est exprimée en AUC ci-dessous.",
    step3t: "Évaluer selon le règlement",
    step3b:
      "Les pics LiDAR de 6 m et plus sur le lot sont notés avec le calibrage, puis cumulés en probabilité qu'au moins un arbre mature s'y trouve, et de même pour la bande voisine de 6 m. Les bâtiments sont masqués de la surface au préalable; le chiffre est donc un signal de dépistage, jamais une décision de permis.",
    accuracyTitle: "Précision (mesurée)",
    accuracyBody: (auc: string, n: string) =>
      `Le calibrage des arbres matures obtient une AUC de ${auc} sur ${n} arbres de rue du quartier 12 au diamètre connu (validation croisée en 5 plis). La détection individuelle des couronnes a d'abord été tentée et a honnêtement échoué : F1 de 0,023 avec DeepForest pré-entraîné, 0,000 après ajustement, et 0,046 par ligne de partage des eaux à 1 m sur des tuiles étiquetées à la main, parce que les cinq millésimes d'orthophotos de la Ville sont des captures printanières sans feuilles. Ce dépistage contourne la détection : il mesure la structure de la canopée, pas les couronnes.`,
  },

  mcp: {
    kicker: "Pour les agents IA",
    title: "Connectez votre agent",
    body: "Le dépistage est offert en MCP (HTTP diffusable) et en API REST simple. Deux outils : canopy_screen prend une adresse et renvoie le dépistage complet; parcel_crowns prend un identifiant de parcelle et renvoie ses données de parcelle (le tableau crowns est réservé à un futur gain de segmentation et est vide pour l'instant). Collez le bloc dans votre harnais et pointez-le vers ce serveur.",
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
      "Ajoutez ce serveur MCP dans ChatGPT (mode Développeur > Outils > Ajouter un serveur MCP) :\n\nURL du serveur : {origin}/mcp\nNom : {displayName}\n\nPuis demandez : « Dépiste {displayName} pour 1843 Eglinton Ave W » ou utilisez canopy_screen avec toute adresse torontoise.",
    pClaude:
      "Connectez ce serveur MCP dans Claude (Paramètres > Intégrations > Ajouter) :\n\nURL du serveur : {origin}/mcp\nNom : {displayName}\n\nPuis demandez-lui de dépister une adresse de Toronto avec canopy_screen, p. ex. 1843 Eglinton Ave W.",
    pClaudeCode:
      "Claude Code se connecte à ce serveur MCP en une commande :\n\nclaude mcp add --transport http {slug} {origin}/mcp\n\nPuis : « Utilise canopy_screen pour dépister 1843 Eglinton Ave W » ou parcel_crowns avec un identifiant de parcelle comme TOP-5293472.",
    pCli:
      "Tout client JSON-RPC 2.0 sur HTTP diffusable fonctionne :\n\ncurl -s -X POST {origin}/mcp \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"canopy_screen\",\"arguments\":{\"address\":\"1843 Eglinton Ave W\"}}}'",
  },

  footer: {
    wordmark: "Open Nshipyard",
    tagline: "Outils de données civiques, open source, construits à Toronto.",
    dataNote: "Dépistage à partir de données ouvertes : LiDAR aéroporté de 2023 via la mosaïque HRDEM de RNCan, points d'adresse et inventaire des arbres de rue de la Ville de Toronto. Ni conseil juridique ni conseil arboricole.",
  },
};

export const STRINGS = { en, fr };
export type Strings = typeof en;
