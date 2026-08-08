/* TeamKits — cores reais de camisa/calção das 44 seleções exportadas.
 * Genérico e permanente: qualquer visualização usa kitsFor(home, away), que
 * devolve os kits com regra de conflito (camisas semelhantes → o visitante
 * troca para um alternativo distante de ambas) e goleiros com cor contrastante.
 */
(function () {
  const K = (shirt, shorts) => ({ shirt, shorts });
  const KITS = {
    "Algeria": K("#FFFFFF", "#FFFFFF"), "Argentina": K("#8EC9EE", "#15181D"),
    "Australia": K("#FFCD00", "#0B6B44"), "Austria": K("#C8102E", "#FFFFFF"),
    "Belgium": K("#C8102E", "#15181D"), "Bosnia & Herzegovina": K("#002F6C", "#FFFFFF"),
    "Brazil": K("#FFDC00", "#1E4785"), "Canada": K("#C8102E", "#C8102E"),
    "Cape Verde Islands": K("#003DA5", "#FFFFFF"), "Colombia": K("#FCD116", "#003893"),
    "Congo DR": K("#0085CA", "#C8102E"), "Croatia": K("#FFFFFF", "#1B4DA1"),
    "Curaçao": K("#002B7F", "#FFFFFF"), "Czech Republic": K("#D6001C", "#FFFFFF"),
    "Ecuador": K("#FFD100", "#003087"), "Egypt": K("#C8102E", "#15181D"),
    "England": K("#FFFFFF", "#001F5C"), "France": K("#002654", "#FFFFFF"),
    "Germany": K("#FFFFFF", "#15181D"), "Ghana": K("#FFFFFF", "#CE1126"),
    "Haiti": K("#00209F", "#D21034"), "Iran": K("#FFFFFF", "#FFFFFF"),
    "Iraq": K("#007A3D", "#FFFFFF"), "Ivory Coast": K("#FF8200", "#FFFFFF"),
    "Japan": K("#001E62", "#FFFFFF"), "Mexico": K("#006847", "#FFFFFF"),
    "Morocco": K("#C1272D", "#006233"), "Netherlands": K("#FF6600", "#FFFFFF"),
    "New Zealand": K("#FFFFFF", "#FFFFFF"), "Norway": K("#C8102E", "#00205B"),
    "Panama": K("#C8102E", "#FFFFFF"), "Paraguay": K("#D0103A", "#1B4DA1"),
    "Portugal": K("#E42518", "#006437"), "Qatar": K("#8A1538", "#FFFFFF"),
    "Saudi Arabia": K("#FFFFFF", "#0B6B44"), "Senegal": K("#FFFFFF", "#0B6B44"),
    "South Africa": K("#FFB81C", "#0B6B44"), "South Korea": K("#E4002B", "#15181D"),
    "Spain": K("#C60B1E", "#1F2A6B"), "Sweden": K("#FFCD00", "#004B87"),
    "Switzerland": K("#DA291C", "#FFFFFF"), "Türkiye": K("#E30A17", "#FFFFFF"),
    "USA": K("#FFFFFF", "#002868"), "Uruguay": K("#7BAFD4", "#15181D"),
  };
  const DEFAULT = K("#8A9099", "#FFFFFF");
  const ALTS = ["#0F7A57", "#3D4DBE", "#C2872C", "#C0322B", "#15181D", "#7A3D8F"];
  const GKS = ["#F2C230", "#57B8B2", "#7A3D8F", "#FF7654", "#8ED081"];

  function rgb(hex) {
    return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }
  function dist(a, b) {
    const [r1, g1, b1] = rgb(a), [r2, g2, b2] = rgb(b);
    return Math.hypot(r1 - r2, g1 - g2, b1 - b2);
  }
  const farFrom = (options, colours, min) =>
    options.find((o) => colours.every((c) => dist(o, c) > min)) || options[0];

  function kitsFor(homeName, awayName) {
    const home = { ...(KITS[homeName] || DEFAULT) };
    const away = { ...(KITS[awayName] || DEFAULT) };
    if (dist(home.shirt, away.shirt) < 90) {
      away.shirt = farFrom(ALTS, [home.shirt, away.shirt], 110);
      away.shorts = "#FFFFFF";
      away.alternate = true;
    }
    home.gk = farFrom(GKS, [home.shirt, away.shirt], 100);
    away.gk = farFrom(GKS.slice().reverse(), [home.shirt, away.shirt, home.gk], 100);
    return { home, away };
  }

  window.TeamKits = { kitsFor, table: KITS };
})();
