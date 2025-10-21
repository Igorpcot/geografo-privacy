"""Ferramenta CLI para gerar arquivos KML a partir de relatórios geoestratégicos.

O script identifica referências espaciais em um texto (ou PDF) utilizando
um catálogo controlado e produz um KML hierárquico com a mesma estrutura
empregada pelo Geógrafo v2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:  # Importação opcional para leitura de PDFs
    from pdfminer.high_level import extract_text  # type: ignore
except Exception:  # pragma: no cover - dependência opcional
    extract_text = None  # type: ignore

import xml.etree.ElementTree as ET
from xml.dom import minidom

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
STYLE_MAP = {
    "country-border": "Países e Fronteiras",
    "city-capital": "Capitais e Cidades",
    "city-major": "Capitais e Cidades",
    "region-zone": "Regiões e Zonas Estratégicas",
    "infrastructure": "Infraestrutura e Recursos",
    "route-line": "Linhas e Rotas Estratégicas",
    "event-operation": "Eventos e Operações",
}
FOLDER_ORDER = [
    "Países e Fronteiras",
    "Capitais e Cidades",
    "Regiões e Zonas Estratégicas",
    "Infraestrutura e Recursos",
    "Linhas e Rotas Estratégicas",
    "Eventos e Operações",
]


def tag(name: str) -> str:
    return f"{{{KML_NAMESPACE}}}{name}"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera um arquivo KML com base em um relatório geoestratégico",
    )
    parser.add_argument(
        "source",
        help="Caminho para o relatório de entrada (TXT ou PDF)",
    )
    parser.add_argument(
        "output",
        help="Caminho de saída do arquivo KML gerado",
    )
    parser.add_argument(
        "--knowledge-base",
        default="data/entities.json",
        help="Caminho para o arquivo JSON com o catálogo de entidades",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Inclui todas as entidades do catálogo independentemente da detecção",
    )
    return parser.parse_args(list(argv))


def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if extract_text is None:
            raise RuntimeError(
                "Suporte a PDF indisponível. Instale 'pdfminer.six' ou converta o arquivo para texto."
            )
        return extract_text(str(path))
    return path.read_text(encoding="utf-8")


def load_knowledge(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entities = data.get("entities")
    if not isinstance(entities, list):
        raise ValueError("Arquivo de conhecimento inválido: campo 'entities' ausente ou incorreto")
    return [entity for entity in entities if isinstance(entity, dict)]


def detect_entities(text: str, knowledge: List[Dict[str, Any]], include_all: bool) -> List[Dict[str, Any]]:
    if include_all:
        return knowledge

    text_lower = text.lower()
    detected: List[Dict[str, Any]] = []
    for entity in knowledge:
        names = [entity.get("name", "")]
        names.extend(entity.get("aliases", []))
        for alias in filter(None, names):
            if alias.lower() in text_lower:
                detected.append(entity)
                break
    return detected


def ensure_folder(document: ET.Element, name: str) -> ET.Element:
    for folder in document.findall(tag("Folder")):
        title = folder.find(tag("name"))
        if title is not None and title.text == name:
            return folder
    folder = ET.SubElement(document, tag("Folder"))
    name_el = ET.SubElement(folder, tag("name"))
    name_el.text = name
    return folder


def add_styles(document: ET.Element) -> None:
    def add_line_style(style_id: str, color: str, width: int, poly_color: str | None = None) -> None:
        style = ET.SubElement(document, tag("Style"), attrib={"id": style_id})
        line = ET.SubElement(style, tag("LineStyle"))
        line_color = ET.SubElement(line, tag("color"))
        line_color.text = color
        width_el = ET.SubElement(line, tag("width"))
        width_el.text = str(width)
        if poly_color is not None:
            poly = ET.SubElement(style, tag("PolyStyle"))
            poly_color_el = ET.SubElement(poly, tag("color"))
            poly_color_el.text = poly_color

    def add_icon_style(style_id: str, color: str, href: str, scale: float = 1.0) -> None:
        style = ET.SubElement(document, tag("Style"), attrib={"id": style_id})
        icon_style = ET.SubElement(style, tag("IconStyle"))
        icon_color = ET.SubElement(icon_style, tag("color"))
        icon_color.text = color
        icon_scale = ET.SubElement(icon_style, tag("scale"))
        icon_scale.text = f"{scale:.1f}"
        icon = ET.SubElement(icon_style, tag("Icon"))
        href_el = ET.SubElement(icon, tag("href"))
        href_el.text = href

    add_line_style("country-border", "ff0055ff", 3, "330055ff")
    add_icon_style(
        "city-capital",
        "ff0000ff",
        "http://maps.google.com/mapfiles/kml/paddle/red-stars.png",
        scale=1.2,
    )
    add_icon_style(
        "city-major",
        "ff00aaff",
        "http://maps.google.com/mapfiles/kml/paddle/blu-circle.png",
        scale=1.1,
    )
    add_line_style("region-zone", "ff00ffaa", 2, "3300ffaa")
    add_icon_style(
        "infrastructure",
        "ff00aa00",
        "http://maps.google.com/mapfiles/kml/paddle/grn-circle.png",
    )
    add_line_style("route-line", "ffffaa00", 4)
    add_icon_style(
        "event-operation",
        "ff00ffff",
        "http://maps.google.com/mapfiles/kml/paddle/purple-blank.png",
        scale=1.1,
    )


def format_coordinates(coords: Iterable[Iterable[float]]) -> str:
    return "\n".join(f"{lon:.6f},{lat:.6f},0" for lon, lat in coords)


def add_geometry(placemark: ET.Element, geometry: Dict[str, Any]) -> None:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            raise ValueError("Coordenadas inválidas para ponto")
        point = ET.SubElement(placemark, tag("Point"))
        coord_el = ET.SubElement(point, tag("coordinates"))
        coord_el.text = f"{coords[0]:.6f},{coords[1]:.6f},0"
    elif gtype == "LineString":
        if not isinstance(coords, list):
            raise ValueError("Coordenadas inválidas para linha")
        line = ET.SubElement(placemark, tag("LineString"))
        tessellate = ET.SubElement(line, tag("tessellate"))
        tessellate.text = "1"
        coord_el = ET.SubElement(line, tag("coordinates"))
        coord_el.text = format_coordinates(coords)
    elif gtype == "Polygon":
        if not isinstance(coords, list):
            raise ValueError("Coordenadas inválidas para polígono")
        polygon = ET.SubElement(placemark, tag("Polygon"))
        outer = ET.SubElement(polygon, tag("outerBoundaryIs"))
        ring = ET.SubElement(outer, tag("LinearRing"))
        coord_el = ET.SubElement(ring, tag("coordinates"))
        coord_el.text = format_coordinates(coords)
    else:
        raise ValueError(f"Tipo de geometria não suportado: {gtype}")


def build_description(entity: Dict[str, Any]) -> str:
    metadata = entity.get("metadata")
    if isinstance(metadata, dict):
        period = metadata.get("period")
        context = metadata.get("context")
        assets = metadata.get("assets")
        lines = []
        if period:
            lines.append(f"Período: {period}")
        if context:
            lines.append(f"Contexto: {context}")
        if assets:
            lines.append(f"Ativos: {assets}")
        return "\n".join(lines)
    description = entity.get("description")
    if not isinstance(description, str):
        return ""
    return description


def add_entity(document: ET.Element, entity: Dict[str, Any]) -> None:
    style = entity.get("style")
    if style not in STYLE_MAP:
        raise ValueError(f"Estilo desconhecido: {style}")
    folder_name = STYLE_MAP[style]
    folder = ensure_folder(document, folder_name)

    placemark = ET.SubElement(folder, tag("Placemark"))
    name_el = ET.SubElement(placemark, tag("name"))
    name_el.text = entity.get("name", "<sem nome>")

    style_el = ET.SubElement(placemark, tag("styleUrl"))
    style_el.text = f"#{style}"

    description = build_description(entity)
    if description:
        desc_el = ET.SubElement(placemark, tag("description"))
        desc_el.text = description

    geometry = entity.get("geometry")
    if not isinstance(geometry, dict):
        raise ValueError(f"Geometria inválida para {entity.get('name')}")
    add_geometry(placemark, geometry)


def build_kml(entities: List[Dict[str, Any]]) -> ET.Element:
    kml = ET.Element(tag("kml"), attrib={"xmlns": KML_NAMESPACE})
    document = ET.SubElement(kml, tag("Document"))
    name_el = ET.SubElement(document, tag("name"))
    name_el.text = "Geógrafo v2 - Produto Gerado"
    open_el = ET.SubElement(document, tag("open"))
    open_el.text = "1"

    add_styles(document)

    # Garante a presença das pastas na ordem correta
    for folder_name in FOLDER_ORDER:
        ensure_folder(document, folder_name)

    for entity in entities:
        add_entity(document, entity)

    return kml


def write_kml(root: ET.Element, output: Path) -> None:
    raw = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    output.write_bytes(pretty)


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    source_path = Path(args.source)
    output_path = Path(args.output)
    knowledge_path = Path(args.knowledge_base)

    if not source_path.exists():
        print(f"[ERRO] Arquivo de entrada '{source_path}' não encontrado.")
        return 1
    if not knowledge_path.exists():
        print(f"[ERRO] Catálogo '{knowledge_path}' não encontrado.")
        return 1

    try:
        text = read_source(source_path)
    except Exception as exc:  # pragma: no cover - erro fatal
        print(f"[ERRO] Falha ao ler relatório: {exc}")
        return 1

    try:
        knowledge = load_knowledge(knowledge_path)
    except Exception as exc:
        print(f"[ERRO] Catálogo inválido: {exc}")
        return 1

    detected = detect_entities(text, knowledge, args.include_all)
    if not detected:
        print("[ALERTA] Nenhuma entidade reconhecida no relatório. Nada foi gerado.")
        return 2

    kml_root = build_kml(detected)
    write_kml(kml_root, output_path)

    print(f"Arquivo KML gerado em: {output_path}")
    print("Entidades incluídas:")
    for entity in detected:
        name = entity.get("name", "<sem nome>")
        style = entity.get("style", "<desconhecido>")
        print(f"  - {name} ({STYLE_MAP.get(style, 'Categoria indefinida')})")

    return 0


if __name__ == "__main__":  # pragma: no cover - entrada padrão
    sys.exit(main(sys.argv[1:]))
