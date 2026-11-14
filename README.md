# Better-DocImage

Pipeline de melhoria de documentos fotografados. O programa corrige a perspectiva, nivela a iluminação, ajusta contraste e nitidez e grava a saída nos modos `color`, `gray` e `bw`, em PNG e, opcionalmente, em PDF.

O projeto começou como um script único e foi refatorado em sete módulos com contratos explícitos, testes unitários e golden outputs. O comportamento observável é congelado por regressão visual: qualquer mudança intencional de qualidade exige atualização explícita do baseline.

## Requisitos

- Python 3.12 ou superior. O baseline foi gerado e validado com Python 3.14.10.
- OpenCV 5.0.0, NumPy 2.5.4 e Pillow 13.0.0, pinados no `pyproject.toml`.
- Nenhuma interface gráfica é necessária; o CLI é o ponto de entrada.

## Instalação

```bash
git clone https://github.com/salomaoeliseu/better-docimage.git
cd better-docimage
python3.14 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

O extra `dev` instala o `pytest` na versão usada pela suíte. Para instalar apenas o pipeline, use `python -m pip install .` ou `python -m pip install -e .`.

Confirme que o entry point foi instalado:

```bash
better-docimage --help
python -m better_docimage --help
```

Os dois comandos executam o mesmo CLI.

## Uso

```bash
better-docimage foto.jpg
```

Por padrão, o comando gera `foto_color.png` e `foto_gray.png` ao lado da imagem de entrada. Para gerar os três modos, PDFs e um prefixo de saída próprio:

```bash
better-docimage foto.jpg -o saida/ficha --modes color,gray,bw --pdf
```

Nesse exemplo, as saídas são `saida/ficha_color.png`, `saida/ficha_color.pdf`, `saida/ficha_gray.png`, `saida/ficha_gray.pdf`, `saida/ficha_bw.png` e `saida/ficha_bw.pdf`.

### Argumentos

| Argumento | Padrão | Descrição |
|---|---|---|
| `input` | obrigatório | imagem de entrada |
| `-o`, `--output` | nome da entrada sem extensão | prefixo dos arquivos de saída |
| `--modes` | `color,gray` | modos separados por vírgula: `color`, `gray`, `bw` |
| `--width` | `2480` | largura alvo da saída em pixels (A4 a 300 DPI) |
| `--gamma` | `1.5` | correção de gamma aplicada ao contraste |
| `--sharpen` | `0.9` | intensidade do unsharp mask; `0` desativa |
| `--denoise` | `4.0` | intensidade do denoise; `0` desativa |
| `--bw-offset` | `0` | deslocamento do limiar de binarização |
| `--corners` | detecção automática | cantos manuais: `TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy` |
| `--pdf` | desligado | também grava PDF com o mesmo DPI do PNG |
| `-v`, `--verbose` | desligado | mostra diagnóstico detalhado em stderr |

O modo `bw` binariza a imagem e pode eliminar traços finos; use `color` ou `gray` quando a fidelidade do traço for prioritária.

Os cantos de `--corners` estão no espaço da imagem original, antes do recorte automático, na ordem superior esquerdo, superior direito, inferior direito e inferior esquerdo:

```bash
better-docimage foto.jpg --corners 120,80,2100,60,2200,2900,90,3000
```

O DPI do PNG e do PDF é derivado da largura alvo (`--width / 8.27`), e não fixado em 300. A altura é proporcional à imagem corrigida.

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | sucesso |
| `1` | erro de processamento ou de leitura/escrita; a mensagem vai para stderr |
| `2` | erro de uso da CLI, detectado antes de qualquer leitura de imagem |

Com `--verbose`, o diagnóstico inclui o traceback da falha de processamento.

## Uso como biblioteca

A fachada `better_docimage` reexporta os contratos e as etapas do pipeline:

```python
from pathlib import Path

from better_docimage import (
    IoParams,
    OutputMode,
    Settings,
    enhance,
    load_image,
    save_png,
)

settings = Settings(target_width=2480, gamma=1.5, sharpen_amount=0.9)
result = enhance(load_image(Path("foto.jpg")), settings, modes=(OutputMode.COLOR,))

io = IoParams()
save_png(
    result[OutputMode.COLOR],
    Path("saida.png"),
    io.dpi_for_width(settings.target_width),
    io,
)
```

`enhance` também aceita `corners` como um array `(4, 2)` no espaço da imagem original e parâmetros opcionais `DetectionParams` e `QualityParams`.

## Testes

```bash
python -m pytest -m fast
python -m pytest -m slow
```

A suíte rápida cobre contratos, geometria, reamostragem, CLI, arquitetura, empacotamento e a estrutura do baseline. Ela não reprocessa as imagens completas e é o gate de todo push/PR.

A suíte lenta reproduz as 18 saídas golden: três imagens de `assets/`, nos modos `color`, `gray` e `bw`, com e sem `--pdf`. As imagens de entrada não são versionadas; se `assets/` estiver ausente, a suíte lenta é pulada com uma mensagem explicando quais arquivos faltam. Detalhes de tolerância, manifest e limitações estão em [tests/README.md](tests/README.md).

Para recriar o baseline de propósito, depois de uma mudança de comportamento aprovada:

```bash
python tests/generate_golden.py
```

Não regenere o baseline para fazer uma regressão passar. O manifest registra versões e plataforma para distinguir os dois casos.

## Estrutura

| Módulo | Responsabilidade |
|---|---|
| `better_docimage/__init__.py` | fachada pública; apenas reexports e `__all__` |
| `better_docimage/__main__.py` | `python -m better_docimage` |
| `better_docimage/cli.py` | parser, validação antecipada, `run` e `main` |
| `better_docimage/settings.py` | `Settings`, `DetectionParams`, `QualityParams`, `IoParams` e constantes |
| `better_docimage/io.py` | `RenderedImage`, leitura e escrita PNG/PDF |
| `better_docimage/primitives.py` | contratos geométricos, recorte, matrizes e reamostragem única |
| `better_docimage/detection.py` | detecção de tabela/perspectiva, estimativa de skew e composição |
| `better_docimage/quality.py` | iluminação, contraste, unsharp e binarização |
| `better_docimage/pipeline.py` | `OutputMode`, `EnhancementResult` e `enhance`; apenas orquestração |

## Reprodutibilidade e CI

- O `pyproject.toml` é a única fonte de dependências, pins e configuração do pytest; os antigos `requirements.txt`, `requirements-dev.txt` e `pytest.ini` foram removidos.
- Os pins exatos reproduzem o ambiente do baseline: Python 3.14.10, OpenCV 5.0.0, NumPy 2.5.4 e Pillow 13.0.0.
- Não há um lock separado: as dependências de runtime são pinadas com `==` e o `pytest` é a única dependência de desenvolvimento, também pinado. As dependências transitivas do pytest não participam da geração das imagens.
- O CI executa a suíte rápida em todo push e pull request. A suíte lenta roda sob demanda ou em job agendado; sem os assets locais, ela é pulada de forma explícita.
- Em ambiente idêntico ao do baseline, o SHA-256 dos PNGs precisa coincidir. Os PDFs são comparados sem `CreationDate`/`ModDate`. Em outras plataformas ou versões, a comparação cai para a miniatura, com tolerância média de `1/255` e máxima de 2 níveis.

## Documentação

- [Roadmap de refatoração](docs/roadmap-refatoracao.md)
- [Índice das ADRs](docs/adr/README.md)
- [Testes, golden outputs e tolerâncias](tests/README.md)
