# Guia de Testes do Geógrafo

Este repositório contém o arquivo `geoestrategico.kml`, que representa o produto final geoespacial gerado pelo agente Geógrafo v2. As orientações abaixo mostram como validar o conteúdo e garantir que o arquivo KML esteja pronto para uso operacional.

## 1. Validação sintática do KML

1. Instale o pacote `libxml2-utils` se ainda não estiver disponível:
   ```bash
   sudo apt-get update && sudo apt-get install -y libxml2-utils
   ```
2. Execute a validação do XML:
   ```bash
   xmllint --noout geoestrategico.kml
   ```
   - **Resultado esperado:** sem mensagens de erro. Qualquer erro sintático será reportado diretamente pelo `xmllint` com o número da linha problemática.

## 2. Visualização no Google Earth Pro

1. Abra o Google Earth Pro (Windows, macOS ou Linux).
2. Acesse **Arquivo > Abrir** e selecione `geoestrategico.kml`.
3. Verifique a estrutura de pastas na barra lateral:
   - Países e Fronteiras
   - Capitais e Cidades
   - Regiões e Zonas Estratégicas
   - Infraestrutura e Recursos
   - Linhas e Rotas Estratégicas
   - Eventos e Operações
4. Explore cada camada confirmando se os ícones, estilos e descrições aparecem conforme o esperado.

## 3. Verificação estrutural com o validador interno

1. Garanta que o Python 3 esteja disponível.
2. Execute o script auxiliar:
   ```bash
   python validate_kml.py geoestrategico.kml
   ```
3. Analise o resumo exibido — o script confirma a presença das pastas obrigatórias e informa a quantidade de placemarks em cada uma.

## 4. Conferência geoespacial básica com GDAL/OGR

1. Instale o GDAL (se não possuir):
   ```bash
   sudo apt-get update && sudo apt-get install -y gdal-bin
   ```
2. Liste as camadas com `ogrinfo`:
   ```bash
   ogrinfo geoestrategico.kml
   ```
3. Opcionalmente, converta para GeoJSON para inspeção adicional:
   ```bash
   ogr2ogr -f GeoJSON geoestrategico.json geoestrategico.kml
   ```
   Em seguida, analise o arquivo `geoestrategico.json` em ferramentas SIG ou scripts personalizados.

## 5. Checklist operacional

- [ ] Todos os elementos possuem nome e descrição coerentes.
- [ ] As coordenadas correspondem às localizações reais indicadas.
- [ ] Os estilos (ícones, cores, espessuras) estão alinhados ao padrão cartográfico/militar desejado.
- [ ] As pastas seguem a hierarquia definida nas diretrizes.

Seguindo estes passos, é possível testar e validar o arquivo KML de forma confiável antes de incorporá-lo a fluxos de trabalho analíticos ou operacionais.
