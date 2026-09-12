"""Contra-Pokédex — dime a qué es débil el rival y con qué pegarle.

Ejecutar:  streamlit run app.py
"""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API = "https://pokeapi.co/api/v2"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "contra-pokedex-mvp/1.0"})

TYPE_COLORS = {
    "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0", "electric": "#F7D02C",
    "grass": "#7AC74C", "ice": "#96D9D6", "fighting": "#C22E28", "poison": "#A33EA1",
    "ground": "#E2BF65", "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
    "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC", "dark": "#705746",
    "steel": "#B7B7CE", "fairy": "#D685AD",
}

TYPE_ES = {
    "normal": "Normal", "fire": "Fuego", "water": "Agua", "electric": "Eléctrico",
    "grass": "Planta", "ice": "Hielo", "fighting": "Lucha", "poison": "Veneno",
    "ground": "Tierra", "flying": "Volador", "psychic": "Psíquico", "bug": "Bicho",
    "rock": "Roca", "ghost": "Fantasma", "dragon": "Dragón", "dark": "Siniestro",
    "steel": "Acero", "fairy": "Hada",
}

STAT_ES = {
    "hp": "HP", "attack": "ATK", "defense": "DEF",
    "special-attack": "SpA", "special-defense": "SpD", "speed": "SPE",
}

CLASS_ES = {"physical": "Físico", "special": "Especial", "status": "Estado"}


# ---------------------------------------------------------------- PokeAPI ---
@st.cache_data(ttl=86400, show_spinner=False)
def get_json(url: str) -> dict:
    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400, show_spinner=False)
def pokemon_index() -> list[str]:
    data = get_json(f"{API}/pokemon?limit=100000")
    return [p["name"] for p in data["results"]]


@st.cache_data(ttl=86400, show_spinner=False)
def get_pokemon(name: str) -> dict:
    return get_json(f"{API}/pokemon/{name}")


@st.cache_data(ttl=86400, show_spinner=False)
def type_matchups(defender_types: tuple[str, ...]) -> dict[str, float]:
    """Multiplicador de cada tipo atacante contra esta combinación defensiva."""
    mult = {t: 1.0 for t in TYPE_COLORS}
    for t in defender_types:
        rel = get_json(f"{API}/type/{t}")["damage_relations"]
        for entry in rel["double_damage_from"]:
            mult[entry["name"]] *= 2
        for entry in rel["half_damage_from"]:
            mult[entry["name"]] *= 0.5
        for entry in rel["no_damage_from"]:
            mult[entry["name"]] *= 0
    return mult


@st.cache_data(ttl=86400, show_spinner=False)
def moves_of_type(type_name: str, scan_limit: int) -> list[dict]:
    """Movimientos ofensivos de un tipo, con su potencia. Escanea los primeros N."""
    refs = get_json(f"{API}/type/{type_name}")["moves"][:scan_limit]
    with ThreadPoolExecutor(max_workers=16) as pool:
        details = list(pool.map(lambda m: get_json(m["url"]), refs))

    out = []
    for m in details:
        if m.get("power") and m["damage_class"]["name"] != "status":
            out.append({
                "move": m["name"].replace("-", " ").title(),
                "type": type_name,
                "power": m["power"],
                "accuracy": m.get("accuracy") or 100,
                "class": CLASS_ES[m["damage_class"]["name"]],
            })
    out.sort(key=lambda m: (-m["power"], -m["accuracy"]))
    return out


# ------------------------------------------------------------------- UI -----
def badge(type_name: str, extra: str = "") -> str:
    color = TYPE_COLORS[type_name]
    label = TYPE_ES[type_name] + (f" {extra}" if extra else "")
    return (
        f"<span style='background:{color};color:#fff;padding:4px 12px;"
        f"border-radius:999px;font-weight:600;font-size:0.85rem;"
        f"margin-right:6px;display:inline-block;margin-bottom:6px'>{label}</span>"
    )


st.set_page_config(page_title="Contra-Pokédex", page_icon="🎯", layout="wide")
st.title("🎯 Contra-Pokédex")
st.caption("Elegí al rival y mirá con qué pegarle. Datos en vivo de PokeAPI.")

scan_limit = st.sidebar.slider(
    "Movimientos a revisar por tipo", 20, 300, 100, 20,
    help="Más movimientos = mejores candidatos, pero la primera carga tarda más.",
)
top_n = st.sidebar.slider("Ataques a mostrar por tipo", 1, 10, 3)

try:
    names = pokemon_index()
except requests.RequestException:
    st.error("No se pudo contactar a PokeAPI. Revisá tu conexión y recargá.")
    st.stop()

choice = st.selectbox(
    "Pokémon rival",
    names,
    index=names.index("garchomp") if "garchomp" in names else 0,
    format_func=lambda n: n.replace("-", " ").title(),
)

with st.spinner("Consultando la Pokédex…"):
    poke = get_pokemon(choice)
    types = tuple(t["type"]["name"] for t in poke["types"])
    mult = type_matchups(types)

sprite = (poke["sprites"]["other"]["official-artwork"]["front_default"]
          or poke["sprites"]["front_default"])

head_img, head_info = st.columns([1, 2])
with head_img:
    if sprite:
        st.image(sprite, width=220)
with head_info:
    st.subheader(f"#{poke['id']} · {choice.replace('-', ' ').title()}")
    st.markdown("".join(badge(t) for t in types), unsafe_allow_html=True)
    st.markdown(
        f"**Altura** {poke['height'] / 10:.1f} m &nbsp;·&nbsp; "
        f"**Peso** {poke['weight'] / 10:.1f} kg &nbsp;·&nbsp; "
        f"**Total base** {sum(s['base_stat'] for s in poke['stats'])}"
    )

st.divider()

# --- Matriz de efectividad --------------------------------------------------
table = pd.DataFrame(
    [{"Tipo": TYPE_ES[t], "type": t, "Multiplicador": m} for t, m in mult.items()]
).sort_values(["Multiplicador", "Tipo"], ascending=[False, True])

weak = table[table["Multiplicador"] > 1]
resist = table[(table["Multiplicador"] < 1) & (table["Multiplicador"] > 0)]
immune = table[table["Multiplicador"] == 0]

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("#### Debilidades")
    st.markdown(
        "".join(badge(r.type, f"×{r.Multiplicador:g}") for r in weak.itertuples())
        or "_Ninguna_", unsafe_allow_html=True,
    )
with c2:
    st.markdown("#### Resistencias")
    st.markdown(
        "".join(badge(r.type, f"×{r.Multiplicador:g}") for r in resist.itertuples())
        or "_Ninguna_", unsafe_allow_html=True,
    )
with c3:
    st.markdown("#### Inmunidades")
    st.markdown(
        "".join(badge(r.type, "×0") for r in immune.itertuples())
        or "_Ninguna_", unsafe_allow_html=True,
    )

with st.expander("Ver tabla completa de efectividad"):
    st.dataframe(
        table[["Tipo", "Multiplicador"]].reset_index(drop=True),
        use_container_width=True, hide_index=True,
    )

st.divider()

# --- Mejores ataques --------------------------------------------------------
st.markdown("### Mejores ataques contra este rival")

if weak.empty:
    st.info("Ningún tipo le pega súper efectivo. Buscá potencia bruta o STAB.")
else:
    rows = []
    prog = st.progress(0.0, text="Buscando movimientos…")
    for i, r in enumerate(weak.itertuples(), start=1):
        for mv in moves_of_type(r.type, scan_limit)[:top_n]:
            rows.append({
                "Ataque": mv["move"],
                "Tipo": TYPE_ES[mv["type"]],
                "Efectividad": f"×{r.Multiplicador:g}",
                "Potencia": mv["power"],
                "Precisión": mv["accuracy"],
                "Categoría": mv["class"],
                "_mult": r.Multiplicador,
            })
        prog.progress(i / len(weak), text=f"Buscando movimientos… {TYPE_ES[r.type]}")
    prog.empty()

    df = (pd.DataFrame(rows)
          .sort_values(["_mult", "Potencia"], ascending=False)
          .drop(columns="_mult")
          .reset_index(drop=True))
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        f"Ordenado por efectividad y luego potencia. Se revisaron los primeros "
        f"{scan_limit} movimientos de cada tipo."
    )

st.divider()

# --- Stats base -------------------------------------------------------------
st.markdown("### Stats base")
stats = {STAT_ES[s["stat"]["name"]]: s["base_stat"] for s in poke["stats"]}
order = ["HP", "ATK", "DEF", "SpA", "SpD", "SPE"]
values = [stats[k] for k in order]

fig = go.Figure(
    go.Bar(
        x=values, y=order, orientation="h",
        marker_color=TYPE_COLORS[types[0]],
        text=values, textposition="outside",
    )
)
fig.update_layout(
    height=320, margin=dict(l=10, r=40, t=10, b=10),
    xaxis=dict(range=[0, max(255, max(values) + 30)], title="Valor base"),
    yaxis=dict(autorange="reversed"), showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)

st.caption("Datos: PokeAPI · pokeapi.co")
