# Testes das fases 0 a 4

Esta suíte congela o comportamento do pipeline antes e depois da extração do pacote. A Fase 0 criou o baseline; a Fase 1 adicionou os contratos explícitos, a validação antecipada e a centralização do tuning sem mover arquivos; a Fase 2 extraiu I/O, CLI e settings para `better_docimage/`; a Fase 3 extraiu geometria, detecção, qualidade e orquestração, sem alterar pixels; a Fase 4 consolidou o empacotamento, os pins e o CI.

## Como rodar

```bash
python -m pip install -e ".[dev]"
python -m pytest -m fast
python -m pytest -m slow
```

Para recriar o baseline de propósito, depois de uma mudança de comportamento aprovada:

```bash
python tests/generate_golden.py
```

`pytest -m fast` é o gate das fases 0 a 4. A suíte `slow` reexecuta o pipeline nas três imagens de `assets/` e por isso fica de fora desse gate. As imagens de entrada não são versionadas: quando `assets/` está ausente, o teste lento é pulado com a lista de arquivos faltantes.

## Estrutura após a Fase 4

O código de produção vive no pacote `better_docimage/`:

| Módulo | Responsabilidade |
|---|---|
| `__init__.py` | fachada pública; apenas reexports e `__all__` |
| `__main__.py` | `python -m better_docimage` |
| `cli.py` | parser, validação antecipada, `run` e `main` |
| `settings.py` | `Settings`, `DetectionParams`, `QualityParams`, `IoParams` e constantes |
| `io.py` | `RenderedImage`, leitura e escrita PNG/PDF |
| `primitives.py` | contratos geométricos, recorte, matrizes e reamostragem única |
| `detection.py` | detecção de tabela/perspectiva, estimativa de skew e composição |
| `quality.py` | iluminação, contraste, unsharp e binarização |
| `pipeline.py` | `OutputMode`, `EnhancementResult` e `enhance`; apenas orquestração |

O wrapper `better_docimage.py` foi removido ao fim da Fase 3. A Fase 4 adicionou o console script `better-docimage`, declarado no `pyproject.toml` e equivalente a `python -m better_docimage`. A suíte lenta usa o entry point de módulo, então o golden continua exercitando o caminho real de processamento; o entry point instalado é verificado por um teste rápido próprio.

O `geometry.py` previsto na ADR-001 não foi mantido como módulo único: ele passaria de ~200 statements e de 30% do total. A divisão seguiu a regra da própria ADR, com `primitives.py` para o núcleo estável e `detection.py` para a parte volátil de detecção e composição.

## Dependências do baseline

O ambiente em que o baseline foi gerado:

| Pacote | Versão pinada | Notas |
|---|---|---|
| `opencv-python` | 5.0.0.93 | `cv2.__version__` é 5.0.0 |
| `numpy` | 2.5.4 | |
| `pillow` | 13.0.0 | |

Os pins estão no `pyproject.toml`, fonte única de dependências desde a Fase 4. Os antigos `requirements.txt` e `requirements-dev.txt` foram removidos. O `pytest==9.2.0` fica no extra `dev`, instalado com `python -m pip install -e ".[dev]"`.

## Golden outputs

`tests/generate_golden.py` roda as três imagens de `assets/` com os padrões da CLI (`--modes color,gray,bw` e `--pdf`). São 18 saídas: 9 PNG e 9 PDF. As imagens de entrada não são versionadas; sem elas, o gerador falha com a lista de arquivos ausentes e o teste lento é pulado. Um teste rápido executa o mesmo caso com e sem `--pdf` e confirma que o PNG é idêntico e que o PDF só aparece quando a flag é usada. O manifest em `tests/golden/manifest.json` guarda, para cada uma:

- SHA-256 do arquivo completo;
- para PDF, também `sha256_normalized`;
- largura, altura, média, percentil 1 e percentil 99 do raster;
- miniatura com lado maior de 600 px em `tests/golden/thumbs/`.

As imagens completas não são versionadas. O PDF reutiliza a miniatura e as estatísticas do PNG do mesmo modo, porque os dois arquivos saem do mesmo array.

### Mudança de metadados na Fase 1

A Fase 1 passou a derivar o DPI de `target_width / 8.27` (ADR-005). Para o alvo padrão de 2480 px, o metadado físico deixa de ser 300 DPI fixo e passa a ser aproximadamente 299,87 DPI. Isso altera os bytes de PNG e PDF e, portanto, os hashes do baseline. Os pixels, as estatísticas e as miniaturas permanecem idênticos; o manifest foi regenerado uma única vez e as miniaturas foram conferidas por SHA-256 antes e depois.

### Fase 3 sem mudança de pixels

A extração de `primitives.py`, `detection.py` e `quality.py`, com `pipeline.py` reduzido a orquestração, não alterou a ordem das operações nem as fórmulas. Os 18 hashes e as miniaturas do manifest continuam válidos; o manifest não foi regenerado.

### Tolerâncias

Na miniatura, em níveis de 8 bits:

- diferença absoluta média ≤ 1/255;
- diferença máxima ≤ 2 níveis.

O hash do arquivo completo só é exigido quando `opencv-python`, `numpy`, `pillow` e a plataforma são os mesmos gravados no manifest. Em outro ambiente a comparação cai para a miniatura. A suíte rápida não exige que o ambiente atual seja idêntico ao do manifest; essa comparação vale apenas para a suíte lenta.

### Limitação do PDF

O Pillow grava `CreationDate` e `ModDate` com a hora da execução. O SHA-256 cru do PDF muda a cada geração e não serve como oráculo. O teste lento compara `sha256_normalized`, com cada `(D:YYYYMMDDHHMMSSZ)` substituído por `(D:NORMALIZED)`. O campo `sha256` continua sendo o hash cru da geração do baseline.

PNG não recebe esse tratamento: o hash cru tem de coincidir no ambiente pinado.

## O que os testes rápidos travam

Pacote e fachada (Fases 2 e 3):

- a fachada `better_docimage` reexporta os contratos, o I/O, o pipeline, a geometria, a qualidade e a CLI a partir dos módulos que os definem;
- os módulos do pacote importam sem ciclos;
- o pacote tem exatamente sete módulos de código e nenhum concentra mais de 30% dos statements (`tests/test_architecture.py`);
- `python -m better_docimage --help` funciona e mostra os argumentos;
- o wrapper `better_docimage.py` não existe mais; `python -m better_docimage` e o console script executam o mesmo CLI.

Empacotamento e documentação (Fase 4):

- o `pyproject.toml` declara o console script `better-docimage = better_docimage.cli:main`;
- os pins exatos de `opencv-python`, `numpy` e `pillow` coincidem com o ambiente gravado no manifest;
- `pytest==9.2.0` está no extra `dev`;
- `requirements.txt` e `requirements-dev.txt` não existem mais; o `pyproject.toml` é a fonte única;
- o README contém instalação, uso, comandos de teste e links para as ADRs e o roadmap;
- quando o pacote está instalado, o console script `better-docimage --help` funciona (o teste é pulado em uma árvore sem instalação).

Contratos da Fase 1:

- `OutputMode` é a única fonte do vocabulário `color`, `gray` e `bw`, e o parser deriva ajuda e validação dela;
- `EnhancementResult` expõe apenas os modos solicitados, na ordem pedida, e `RenderedImage.is_binary` carrega a semântica binária;
- `Size`, `Offset`, `TransformPlan` e `PreparedInput` substituem tuplas posicionais nas fronteiras;
- `enhance` não calcula `gray`/`bw` quando apenas `color` é pedido, nem `bw` quando apenas `gray` é pedido;
- o DPI é derivado da largura alvo e o I/O não varre pixels para decidir se a imagem é binária.

Geometria (`primitives.py` e `detection.py`), com matrizes controladas:

- `combined = fine_rotation @ crop_matrix @ geometry`;
- essa ordem não é intercambiável;
- um ponto transformado pela matriz combinada coincide com a aplicação passo a passo;
- sem detecção e com skew zero, a combinada é a identidade;
- `prepare_input` é o único ponto que converte `--corners` da imagem original para a imagem recortada;
- imagem sem margens mantém offset zero, imagem totalmente branca devolve offset zero e cantos fora do recorte não são truncados.

Reamostragem (`primitives.py`):

- `warp_and_upscale_once` chama `warpPerspective` uma vez;
- `enhance` chama esse caminho final uma vez.

A prévia geométrica pode chamar `warpPerspective` à parte. Essa chamada não produz a imagem de saída e não entra na contagem do caminho final.

CLI, depois da validação antecipada (ADR-004):

| Caso | Resultado travado |
|---|---|
| `--modes` desconhecido | código 2, antes de abrir a imagem |
| `--modes` vazio | código 2, antes de abrir a imagem |
| `--modes` duplicado | código 0, o modo é gravado uma vez |
| `--corners` inválido | código 2, sem traceback |
| `--sharpen` negativo | código 2 |
| `--denoise` negativo | código 2 |
| `--gamma 0` ou `--width 0` | código 2 |
| `--gamma` não finito ou `--corners` com `NaN`/`inf` | código 2 |
| imagem ausente | código 1, log em stderr, sem traceback |

Fallbacks de detecção e diagnóstico usam `logging` em stderr; `--verbose` aumenta o nível. O `print` de status (`ok -> ...`) permanece apenas na camada de CLI.

## CI

O workflow `.github/workflows/ci.yml` tem dois jobs:

- `fast`: roda em todo push e pull request; instala `-e ".[dev]"`, executa `pip check`, verifica os dois entry points e roda `pytest -m fast`.
- `slow`: roda sob demanda (`workflow_dispatch`) e semanalmente; instala o pacote e roda `pytest -m slow`. Como `assets/` não é versionado, o teste é pulado no runner padrão com a razão explícita. Para executá-lo de verdade no CI, provisione as três imagens no workspace antes do passo.

## Recriar o baseline

Só rode `python tests/generate_golden.py` quando a mudança de comportamento for intencional. O script exige as três imagens de `assets/`, que não são versionadas. Uma mudança de hash no ambiente pinado é regressão, não ruído, exceto quando acompanhada de mudança de metadado documentada como a do DPI acima.
