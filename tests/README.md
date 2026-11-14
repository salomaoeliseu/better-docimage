# Testes da fase 0

Esta suíte congela o comportamento de `better_docimage_refactored.py` antes da refatoração. O script de produção não é alterado aqui.

## Como rodar

```bash
python -m pip install -r requirements-dev.txt
python tests/generate_golden.py   # só para recriar o baseline de propósito
pytest -m fast
pytest -m slow
```

`pytest -m fast` é o gate da fase 0. A suíte `slow` reexecuta o pipeline nas três imagens de `assets/` e por isso fica de fora desse gate.

## Dependências do baseline

O ambiente em que o baseline foi gerado:

| Pacote | Versão pinada | Notas |
|---|---|---|
| `opencv-python` | 5.0.0.93 | `cv2.__version__` é 5.0.0 |
| `numpy` | 2.5.4 | |
| `pillow` | 13.0.0 | |

Os pins estão em `requirements.txt`. `pytest==9.2.0` está em `requirements-dev.txt` e entra no `pyproject.toml` na fase 4.

## Golden outputs

`tests/generate_golden.py` roda as três imagens de `assets/` com os padrões da CLI (`--modes color,gray,bw` e `--pdf`). São 18 saídas: 9 PNG e 9 PDF. Um teste rápido executa o mesmo caso com e sem `--pdf` e confirma que o PNG é idêntico e que o PDF só aparece quando a flag é usada. O manifest em `tests/golden/manifest.json` guarda, para cada uma:

- SHA-256 do arquivo completo;
- para PDF, também `sha256_normalized`;
- largura, altura, média, percentil 1 e percentil 99 do raster;
- miniatura com lado maior de 600 px em `tests/golden/thumbs/`.

As imagens completas não são versionadas. O PDF reutiliza a miniatura e as estatísticas do PNG do mesmo modo, porque os dois arquivos saem do mesmo array.

### Tolerâncias

Na miniatura, em níveis de 8 bits:

- diferença absoluta média ≤ 1/255;
- diferença máxima ≤ 2 níveis.

O hash do arquivo completo só é exigido quando `opencv-python`, `numpy`, `pillow` e a plataforma são os mesmos gravados no manifest. Em outro ambiente a comparação cai para a miniatura. A suíte rápida não exige que o ambiente atual seja idêntico ao do manifest; essa comparação vale apenas para a suíte lenta.

### Limitação do PDF

O Pillow grava `CreationDate` e `ModDate` com a hora da execução. O SHA-256 cru do PDF muda a cada geração e não serve como oráculo. O teste lento compara `sha256_normalized`, com cada `(D:YYYYMMDDHHMMSSZ)` substituído por `(D:NORMALIZED)`. O campo `sha256` continua sendo o hash cru da geração do baseline.

PNG não recebe esse tratamento: o hash cru tem de coincidir no ambiente pinado.

## O que os testes rápidos travam

Geometria, com matrizes controladas:

- `combined = fine_rotation @ crop_matrix @ geometry`;
- essa ordem não é intercambiável;
- um ponto transformado pela matriz combinada coincide com a aplicação passo a passo;
- sem detecção e com skew zero, a combinada é a identidade;
- `--corners` é convertido subtraindo `original_crop_offset` dentro de `build_combined_transform`. `prepare_input` ainda não existe; isso é a fase 1.

Reamostragem:

- `warp_and_upscale_once` chama `warpPerspective` uma vez;
- `enhance` chama esse caminho final uma vez.

A prévia geométrica pode chamar `warpPerspective` à parte. Essa chamada não produz a imagem de saída e não entra na contagem do caminho final.

CLI, comportamento atual (a fase 1 muda estes casos; ver ADR-004):

| Caso | Resultado travado |
|---|---|
| `--modes` desconhecido | código 2, depois do processamento |
| `--modes` vazio | código 0, sem arquivos |
| `--modes` duplicado | código 0, o modo é gravado duas vezes |
| `--corners` inválido | código 1, com traceback |
| `--sharpen` negativo | código 0; o unsharp é desligado |
| `--gamma 0` | código 2, antes de abrir a imagem |

## Recriar o baseline

Só rode `python tests/generate_golden.py` quando a mudança de comportamento for intencional. Uma mudança de hash no ambiente pinado é regressão, não ruído.
