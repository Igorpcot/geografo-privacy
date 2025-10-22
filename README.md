# Guia Operacional do Geógrafo v2

Este repositório abriga o agente CLI utilizado para transformar relatórios geoestratégicos em um arquivo KML estruturado. A árvore gerada segue o padrão temático exigido (fronteiras, cidades, regiões estratégicas, infraestrutura, rotas e operações) e pode ser validada com as ferramentas incluídas.

> 🔎 Para a doutrina completa do agente, incluindo tarefas geoespaciais prioritárias e regras de governança de dados, consulte o documento [Geógrafo v2 – Identidade e Doutrina Operacional](docs/geografo_identity_doctrine.md).

## 1. Preparação do ambiente

1. Garanta que o Python 3.9+ esteja instalado.
2. (Opcional, para leitura direta de PDFs) instale a dependência adicional:
   ```bash
   pip install pdfminer.six
   ```
3. Clone ou atualize este repositório e navegue até a pasta raiz.

## 2. Gerar um KML a partir de um relatório

Exemplo mínimo utilizando o relatório de demonstração em `samples/exemplo_relatorio.txt`:

```bash
python geografo_agent.py samples/exemplo_relatorio.txt saida.kml
```

A execução exibe a lista de entidades reconhecidas e gera `saida.kml` com a hierarquia completa do Geógrafo v2. Utilize `--include-all` para exportar o catálogo completo independentemente do texto analisado.

### Entrada em PDF

Se o utilitário `pdfminer.six` estiver instalado, o agente lê PDFs diretamente. Arquivos RTF
são suportados nativamente:

```bash
python geografo_agent.py relatorio.pdf saida.kml
python geografo_agent.py relatorio.rtf saida.kml
```

Na ausência da dependência, converta o PDF para texto antes de executar o agente.

## 3. Validação estrutural do KML

Use o validador interno para confirmar a presença das pastas obrigatórias e contabilizar os placemarks:

```bash
python validate_kml.py saida.kml
```

O script falha com código de saída diferente de zero se o arquivo estiver corrompido ou se alguma pasta obrigatória estiver ausente.

## 4. Diagnóstico e logging da execução

Para auditar o fluxo completo, habilite o relatório de diagnóstico e a gravação de logs:

```bash
python geografo_agent.py samples/exemplo_relatorio.txt saida.kml \
  --diagnostics --log-file logs/ultima_execucao.log --log-level DEBUG
```

O diagnóstico apresenta a cobertura por pasta temática, volume de entidades detectadas, tamanho do relatório processado e duplicidades. Os logs registram cada etapa do pipeline (ingestão, carga do catálogo, detecção, escrita do KML) seguindo o nível definido.

## 5. Validações externas recomendadas

1. **Validação sintática com `xmllint`:**
   ```bash
   sudo apt-get update && sudo apt-get install -y libxml2-utils
   xmllint --noout saida.kml
   ```
2. **Inspeção com GDAL/OGR:**
   ```bash
   sudo apt-get update && sudo apt-get install -y gdal-bin
   ogrinfo saida.kml
   ogr2ogr -f GeoJSON saida.json saida.kml
   ```

## 6. Checklist operacional

- [ ] Todos os elementos possuem nome e descrição coerentes.
- [ ] As coordenadas correspondem às localizações reais indicadas.
- [ ] Os estilos (ícones, cores, espessuras) seguem o padrão cartográfico/militar.
- [ ] As pastas estão organizadas conforme as diretrizes do Geógrafo v2.

Seguindo estes passos o agente fica pronto para gerar, validar e entregar produtos KML compatíveis com fluxos de análise geoespacial.
