"""Ferramenta de validação estrutural para o arquivo geoestrategico.kml.

Este script verifica se o documento KML contém o `Document` principal, as
pastas obrigatórias definidas pelas diretrizes operacionais e contabiliza os
placemarks de cada pasta. É um complemento às verificações sintáticas
executadas com utilitários externos (como `xmllint`).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


KML_NAMESPACE = "{http://www.opengis.net/kml/2.2}"


def _tag(name: str) -> str:
    """Retorna o nome da tag com namespace KML 2.2."""

    return f"{KML_NAMESPACE}{name}"


REQUIRED_FOLDERS = [
    "Países e Fronteiras",
    "Capitais e Cidades",
    "Regiões e Zonas Estratégicas",
    "Infraestrutura e Recursos",
    "Linhas e Rotas Estratégicas",
    "Eventos e Operações",
]


def load_tree(path: str) -> ET.ElementTree:
    """Carrega o KML informado.

    Levanta um ValueError com mensagem amigável caso o arquivo não seja um
    KML válido.
    """

    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:  # pragma: no cover - erro fatal
        raise ValueError(f"Falha ao abrir ou interpretar '{path}': {exc}") from exc
    return tree


def find_document(tree: ET.ElementTree) -> ET.Element:
    """Retorna o elemento `<Document>` raiz e valida sua existência."""

    root = tree.getroot()
    document = root.find(_tag("Document"))
    if document is None:
        raise ValueError("Documento KML não contém elemento <Document> raiz")
    return document


def folder_summary(document: ET.Element) -> dict[str, int]:
    """Retorna um resumo com a contagem de placemarks por pasta."""

    summary: dict[str, int] = {}
    for folder in document.findall(_tag("Folder")):
        name_el = folder.find(_tag("name"))
        if name_el is None or not name_el.text:
            folder_name = "<sem nome>"
        else:
            folder_name = name_el.text.strip()
        placemarks = folder.findall(_tag("Placemark"))
        summary[folder_name] = len(placemarks)
    return summary


def extract_extended_data(document: ET.Element) -> dict[str, str]:
    """Obtém metadados do elemento `<ExtendedData>` do documento."""

    payload: dict[str, str] = {}
    extended = document.find(_tag("ExtendedData"))
    if extended is None:
        return payload

    for data_el in extended.findall(_tag("Data")):
        name = data_el.attrib.get("name", "")
        value_el = data_el.find(_tag("value"))
        if not name:
            continue
        if value_el is None or value_el.text is None:
            payload[name] = ""
        else:
            payload[name] = value_el.text.strip()
    return payload


def validate_required_folders(summary: dict[str, int]) -> list[str]:
    """Lista as pastas obrigatórias ausentes."""

    missing = [folder for folder in REQUIRED_FOLDERS if folder not in summary]
    return missing


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python validate_kml.py <caminho_para_kml>")
        return 1

    kml_path = argv[1]
    try:
        tree = load_tree(kml_path)
        document = find_document(tree)
    except ValueError as exc:
        print(f"[ERRO] {exc}")
        return 1

    metadata = extract_extended_data(document)
    summary = folder_summary(document)
    missing = validate_required_folders(summary)

    if metadata:
        print("Metadados do documento:")
        for key, value in metadata.items():
            print(f"  - {key}: {value}")
        print()

    print("Resumo das pastas encontradas:")
    for folder_name, count in summary.items():
        print(f"  - {folder_name}: {count} placemarks")

    if missing:
        print("\n[ALERTA] Pastas obrigatórias ausentes:")
        for folder in missing:
            print(f"  - {folder}")
        return 2

    print("\nValidação concluída: todas as pastas obrigatórias estão presentes.")
    return 0


if __name__ == "__main__":  # pragma: no cover - ponto de entrada do script
    sys.exit(main(sys.argv))

