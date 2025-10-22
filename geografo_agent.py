"""Ferramenta CLI para gerar arquivos KML a partir de relatórios geoestratégicos.

O script identifica referências espaciais em um texto (ou PDF) utilizando
um catálogo controlado e produz um KML hierárquico com a mesma estrutura
empregada pelo Geógrafo v2.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
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
        help="Caminho para o relatório de entrada (TXT, RTF ou PDF)",
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
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Exibe relatório de diagnóstico ao final da execução",
    )
    parser.add_argument(
        "--log-file",
        help="Grava logs detalhados da execução no caminho indicado",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Define o nível de detalhamento dos logs (padrão: INFO)",
    )
    return parser.parse_args(list(argv))


def configure_logging(level_name: str, log_file: str | None) -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("geografo_agent")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.debug("Logger configurado com nível %s", logging.getLevelName(level))
    return logger


def _rtf_to_text(raw: str) -> str:
    """Converte conteúdo RTF em texto plano respeitando os comandos básicos."""

    i = 0
    length = len(raw)
    stack: List[tuple[int, bool]] = []
    result: List[str] = []
    ignorable = False
    ucskip = 1
    curskip = 0

    ignorable_destinations = {
        "fonttbl",
        "colortbl",
        "datastore",
        "stylesheet",
        "info",
        "pict",
        "header",
        "footer",
        "object",
        "filetbl",
        "pntext",
    }

    while i < length:
        char = raw[i]

        if char == "\\":
            i += 1
            if i >= length:
                break
            command = raw[i]

            if command in "\\{}":
                if not ignorable:
                    result.append(command)
                i += 1
                continue

            if command == "*":
                ignorable = True
                i += 1
                continue

            if command == "'":
                hex_value = raw[i + 1 : i + 3]
                if not ignorable and len(hex_value) == 2:
                    try:
                        result.append(bytes.fromhex(hex_value).decode("latin1"))
                    except ValueError:
                        pass
                i += 3
                if curskip > 0:
                    curskip -= 1
                continue

            match = re.match(r"([a-zA-Z]+)(-?\d+)? ?", raw[i:])
            if not match:
                i += 1
                continue
            word = match.group(1)
            arg = match.group(2)
            i += match.end()

            if word in {"par", "line"}:
                if not ignorable:
                    result.append("\n")
                curskip = 0
            elif word == "tab":
                if not ignorable:
                    result.append("\t")
                curskip = 0
            elif word == "uc" and arg is not None:
                try:
                    ucskip = max(int(arg), 0)
                except ValueError:
                    pass
                curskip = 0
            elif word == "u" and arg is not None:
                try:
                    code = int(arg)
                except ValueError:
                    code = None
                if code is not None:
                    if code < 0:
                        code += 0x10000
                    if not ignorable:
                        result.append(chr(code))
                curskip = ucskip
            elif word in ignorable_destinations:
                ignorable = True
                curskip = 0
            else:
                curskip = 0

            if arg is None and raw[i - 1] != " ":
                continue

        elif char == "{":
            stack.append((ucskip, ignorable))
            ignorable = False
            i += 1
            continue
        elif char == "}":
            if stack:
                ucskip, ignorable = stack.pop()
            i += 1
            continue
        else:
            if curskip > 0:
                curskip -= 1
                i += 1
                continue
            if not ignorable:
                result.append(char)
            i += 1
            continue

        if curskip > 0:
            skip = min(curskip, length - i)
            i += skip
            curskip -= skip

    text = "".join(result)
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if extract_text is None:
            raise RuntimeError(
                "Suporte a PDF indisponível. Instale 'pdfminer.six' ou converta o arquivo para texto."
            )
        return extract_text(str(path))
    if suffix == ".rtf":
        return _rtf_to_text(path.read_text(encoding="latin-1"))
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


def run_diagnostics(
    detected: List[Dict[str, Any]],
    knowledge: List[Dict[str, Any]],
    text: str,
) -> Dict[str, Any]:
    coverage: Dict[str, int] = {name: 0 for name in FOLDER_ORDER}
    duplicates: Dict[str, int] = {}

    for entity in detected:
        name = entity.get("name")
        style = entity.get("style")
        folder = STYLE_MAP.get(style)
        if folder in coverage:
            coverage[folder] += 1
        if isinstance(name, str):
            key = name.strip().lower()
            if not key:
                continue
            duplicates[key] = duplicates.get(key, 0) + 1

    missing_categories = [folder for folder, count in coverage.items() if count == 0]
    repeated_entities = [name for name, count in duplicates.items() if count > 1]

    return {
        "catalog_size": len(knowledge),
        "detected_count": len(detected),
        "text_length": len(text),
        "coverage": coverage,
        "missing_categories": missing_categories,
        "repeated_entities": repeated_entities,
    }


def format_diagnostics(report: Dict[str, Any]) -> List[str]:
    lines = [
        "=== Diagnóstico Operacional ===",
        f"Catálogo disponível: {report['catalog_size']} entidades",
        f"Entidades reconhecidas: {report['detected_count']}",
        f"Tamanho do relatório (caracteres): {report['text_length']}",
        "Cobertura por pasta:",
    ]
    for folder in FOLDER_ORDER:
        lines.append(f"  - {folder}: {report['coverage'].get(folder, 0)}")

    missing = report.get("missing_categories", [])
    if missing:
        lines.append("Pastas sem entidades:")
        for folder in missing:
            lines.append(f"  - {folder}")
    else:
        lines.append("Todas as pastas possuem registros.")

    duplicates = report.get("repeated_entities", [])
    if duplicates:
        lines.append("Entidades repetidas:")
        for name in duplicates:
            lines.append(f"  - {name}")
    else:
        lines.append("Nenhuma entidade duplicada detectada.")

    return lines


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
    logger = configure_logging(args.log_level, args.log_file)
    source_path = Path(args.source)
    output_path = Path(args.output)
    knowledge_path = Path(args.knowledge_base)

    logger.info("Iniciando processamento do relatório: %s", source_path)

    if not source_path.exists():
        logger.error("Arquivo de entrada '%s' não encontrado", source_path)
        print(f"[ERRO] Arquivo de entrada '{source_path}' não encontrado.")
        return 1
    if not knowledge_path.exists():
        logger.error("Catálogo '%s' não encontrado", knowledge_path)
        print(f"[ERRO] Catálogo '{knowledge_path}' não encontrado.")
        return 1

    try:
        text = read_source(source_path)
        logger.info("Relatório carregado com %d caracteres", len(text))
    except Exception as exc:  # pragma: no cover - erro fatal
        logger.exception("Falha ao ler relatório")
        print(f"[ERRO] Falha ao ler relatório: {exc}")
        return 1

    try:
        knowledge = load_knowledge(knowledge_path)
        logger.info("Catálogo carregado com %d entidades", len(knowledge))
    except Exception as exc:
        logger.exception("Catálogo inválido")
        print(f"[ERRO] Catálogo inválido: {exc}")
        return 1

    detected = detect_entities(text, knowledge, args.include_all)
    logger.info("Entidades detectadas: %d", len(detected))
    if not detected:
        logger.warning("Nenhuma entidade reconhecida; encerrando sem gerar KML")
        print("[ALERTA] Nenhuma entidade reconhecida no relatório. Nada foi gerado.")
        return 2

    kml_root = build_kml(detected)
    write_kml(kml_root, output_path)
    logger.info("Arquivo KML gravado em %s", output_path)

    print(f"Arquivo KML gerado em: {output_path}")
    print("Entidades incluídas:")
    for entity in detected:
        name = entity.get("name", "<sem nome>")
        style = entity.get("style", "<desconhecido>")
        print(f"  - {name} ({STYLE_MAP.get(style, 'Categoria indefinida')})")

    if args.diagnostics:
        report = run_diagnostics(detected, knowledge, text)
        logger.debug("Relatório de diagnóstico: %s", report)
        for line in format_diagnostics(report):
            print(line)

    return 0


if __name__ == "__main__":  # pragma: no cover - entrada padrão
    sys.exit(main(sys.argv[1:]))
