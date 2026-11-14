# Roadmap de refatoração estrutural — Better-DocImage

- **Data**: 2026-11-13
- **Status**: Fases 0, 1, 2, 3 e 4 concluídas; primeira execução remota do CI pendente de push/PR
- **ADRs**: [001](adr/001-pacote-modular-por-responsabilidade.md) a [006](adr/006-golden-outputs-antes-da-refatoracao.md)
- **Objetivo**: melhorar manutenibilidade, testabilidade e clareza estrutural **sem alterar o comportamento observável** do pipeline.

## Baseline

| Métrica                            | Valor em 2026-11-13                       |
| ---------------------------------- | ----------------------------------------- |
| Módulos de código                  | 1 (`better_docimage.py`)                  |
| Linhas                             | 565                                       |
| Funções                            | 19                                        |
| Statements (AST)                   | 254                                       |
| Testes automatizados               | 0                                         |
| Maior componente lógico            | Detecção geométrica — 94 statements (37%) |
| Dependências observadas no `.venv` | OpenCV 5.0.0, NumPy 2.5.4, Pillow 13.0.0  |
| Dependências declaradas            | `requirements.txt` sem versões pinadas    |

## Escopo

- Contratos explícitos nas fronteiras do pipeline.
- Formalização do espaço de coordenadas dos cantos.
- Validação antecipada e política única de erros/logging.
- Centralização de parâmetros de tuning e metadados de saída.
- Extração incremental para o pacote `better_docimage`.
- Rede de segurança com testes unitários e golden outputs.
- Empacotamento, pinagem de dependências e CI.

## Fora de escopo

- Novos algoritmos ou mudanças intencionais de qualidade de imagem.
- Novas flags de CLI além das necessárias para validação.
- GUI, API HTTP ou processamento em lote.
- Otimização de performance além do que a extração exigir.
- Mudança da invariante de reamostragem única.

## Princípios de execução

1. **Contratos antes de mover arquivos.** Não aumentar a distância de acoplamentos ainda implícitos.
2. **Estável primeiro, volátil depois.** I/O e CLI saem antes de geometria e qualidade.
3. **Comportamento congelado.** Nenhuma fase altera a saída além da tolerância acordada.
4. **Uma fase, um commit/PR reversível.** Sem refatoração e mudança de comportamento no mesmo passo.
5. **Sem over-decomposition.** Seis a sete módulos; `geometry.py` só se divide acima de ~200 statements.
6. **Gate verde.** A fase seguinte não começa sem os critérios de aceite da anterior.

## Visão geral das fases

| Fase | Foco | ADRs | Esforço estimado | Gate principal |
|---|---|---|---|---|
| 0 | Baseline, golden outputs e testes | 006 | 1–2 dias | Suíte verde na versão atual |
| 1 | Contratos, validação, erros e tuning | 002–005 | 2–3 dias | Sem contratos implícitos; golden preservado |
| 2 | Extrair I/O, CLI e settings | 001, 004 | 1–2 dias | CLI idêntica; `python -m` funciona |
| 3 | Extrair geometria, qualidade e pipeline | 001 | 2–3 dias | Sem módulo >30%; golden preservado |
| 4 | Empacotamento, pinagem e CI | 001, 006 | 1 dia | Instalação limpa reproduz o baseline |

**Total estimado:** 7–11 dias de trabalho focado, sem contar revisão.

---

## Fase 0 — Baseline e rede de segurança

**Objetivo:** provar que a versão atual funciona e congelar seu comportamento antes de qualquer mudança.

**Concluída em 2026-11-13.** Suíte rápida e suíte lenta verdes no ambiente pinado (Python 3.14.10, macOS, OpenCV 5.0.0, NumPy 2.5.4, Pillow 13.0.0).

### Tarefas

- [x] Criar `tests/` e configurar `pytest` com markers `fast` e `slow`.
- [x] Pinar as versões atuais das dependências para o baseline (OpenCV 5.0.0, NumPy 2.5.4, Pillow 13.0.0 ou faixas compatíveis).
- [x] Gerar golden outputs para as três imagens de `assets/` nos modos `color`, `gray` e `bw`, com e sem `--pdf` (18 saídas).
- [x] Salvar em `tests/golden/` apenas: hash SHA-256 da saída completa, dimensões, média/p1/p99 e miniatura com lado maior de 600 px. Não versionar as imagens completas.
- [x] Testes exatos de geometria: composição `fine_rotation @ crop_matrix @ geometry`, identidade, ordem de aplicação e conversão de cantos.
- [x] Teste da invariante de reamostragem: o caminho final chama `warpPerspective` exatamente uma vez.
- [x] Testes de CLI: `--modes` inválido/vazio/duplicado, `--corners` inválido, `--sharpen` negativo, `--gamma` zero.
- [x] Documentar as tolerâncias iniciais: diferença média ≤ 1/255 e diferença máxima ≤ 2 níveis nas miniaturas; hash completo só com dependências idênticas.

### Critérios de aceite

- [x] `pytest -m fast` verde na versão atual.
- [x] As 18 saídas baseline são reproduzíveis no ambiente pinado.
- [x] Nenhuma alteração em `better_docimage.py`.
- [x] Tolerâncias e limitações registradas em `tests/README.md`.

### Riscos

- O denoise em imagem cheia pode tornar a geração lenta: gerar baseline uma vez, versionar apenas métricas e miniaturas, e marcar a suíte pesada como `slow`.
- Variação entre plataformas: comparar hash apenas no mesmo ambiente; usar tolerância nas miniaturas.

---

## Fase 1 — Contratos, validação, erros e tuning

**Objetivo:** eliminar os acoplamentos implícitos antes de qualquer extração de arquivo. Nenhum módulo é movido nesta fase.

**Concluída em 2026-11-14.** A suíte rápida e os 18 golden outputs passaram no ambiente pinado. Os pixels e as miniaturas permaneceram idênticos; o manifest foi regenerado porque o DPI passou a ser derivado de `target_width / 8.27`, alterando apenas metadados de PNG/PDF.

### Tarefas

- [x] Implementar `OutputMode`, `EnhancementResult`, `Size`, `Offset`, `TransformPlan` e `RenderedImage` (ADR-002).
- [x] Fazer `enhance` calcular apenas os modos solicitados e o argparse derivar `choices` do enum.
- [x] Implementar `prepare_input` e remover `original_crop_offset` de `build_combined_transform` (ADR-003).
- [x] Separar `build_parser()` e `run(args)`; validar todos os argumentos antes de `load_image` (ADR-004).
- [x] Adotar `argparse.ArgumentTypeError`/`parser.error` para erros de uso e `logging` em stderr para diagnóstico e fallbacks.
- [x] Substituir `print("aviso: ...")` por log com motivo do fallback.
- [x] Criar `DetectionParams`, `QualityParams` e `IoParams`; remover constantes mágicas dos corpos das funções (ADR-005).
- [x] Derivar DPI de `target_width / 8.27` e centralizar a conversão para PIL; remover `quality=92` morto.
- [x] Atualizar testes e confirmar golden outputs dentro da tolerância.

### Critérios de aceite

- [x] Nenhum `dict[str, np.ndarray]` cruza a fronteira do pipeline.
- [x] Nenhuma função retorna `(ndarray, (width, height))` ou offset como tupla posicional.
- [x] Argumento inválido falha antes de qualquer leitura de imagem, com código 2 e sem traceback.
- [x] Nenhum `print` dentro de funções de biblioteca.
- [x] Golden outputs passam sem mudança de comportamento.
- [x] Um modo novo exige uma única edição no enum.

### Riscos

- A migração de contratos toca quase todas as funções: fazer em commits pequenos por contrato e rodar os testes a cada passo.
- A mudança de validação pode alterar mensagens de erro existentes; documentar no PR.

---

## Fase 2 — Extrair I/O, CLI e settings

**Objetivo:** criar o pacote e mover primeiro o código estável e de baixa volatilidade.

**Concluída em 2026-11-14.** O pacote `better_docimage/` agora contém `settings.py`, `io.py`, `pipeline.py` e `cli.py`, além da fachada em `__init__.py` e do entry point em `__main__.py`. Geometria e qualidade permanecem temporariamente em `pipeline.py`, como previsto. A suíte rápida, os 18 golden outputs e a paridade entre `python better_docimage.py` e `python -m better_docimage` passaram no ambiente pinado.

### Tarefas

- [x] Criar `better_docimage/` com `__init__.py` de fachada e `__main__.py`.
- [x] Mover `load_image`, `save_png`, `save_pdf` e `RenderedImage` para `io.py`.
- [x] Mover parser, validação e `run` para `cli.py`.
- [x] Mover `Settings` e as dataclasses de tuning para `settings.py`.
- [x] Manter `enhance` em `pipeline.py`; geometria e qualidade permanecem temporariamente nesse módulo até a Fase 3.
- [x] Atualizar imports e testes; manter `python better_docimage.py` funcionando como wrapper temporário ou remover após validação.
- [x] Adicionar `python -m better_docimage` e testar `--help`.

### Critérios de aceite

- [x] Comportamento da CLI idêntico ao da versão anterior, exceto pelas validações novas.
- [x] `python -m better_docimage` e o entry point temporário funcionam.
- [x] Golden outputs passam.
- [x] Sem imports circulares.
- [x] `__init__.py` não contém lógica de domínio.

### Riscos

- Dois caminhos de import durante a migração: manter um único ponto de reexport e remover o wrapper no fim da fase.
- `settings.py` pode virar depósito: limitar a configuração e parâmetros, sem funções de processamento.

---

## Fase 3 — Extrair geometria, qualidade e pipeline

**Objetivo:** mover o núcleo volátil depois que os contratos já estão explícitos e testados.

**Concluída em 2026-11-14.** O núcleo foi extraído para `primitives.py` (contratos, matrizes, recorte e reamostragem), `detection.py` (detecção e composição), `quality.py` (iluminação, contraste, nitidez e binário) e `pipeline.py` (apenas `OutputMode`, `EnhancementResult` e orquestração). `geometry.py` foi avaliado em ~200 statements e dividido em `primitives.py` e `detection.py`, conforme a regra da ADR-001. O pacote ficou com sete módulos de código; o maior é `detection.py`, com 142 de 511 statements (27,8%). O wrapper `better_docimage.py` foi removido e `python -m better_docimage` passou a ser o único entry point. A suíte rápida (49 testes), os 18 golden outputs e o gate estrutural de `tests/test_architecture.py` passaram no ambiente pinado.

### Tarefas

- [x] Mover funções de matriz, recorte e detecção para `geometry.py`; a avaliação de tamanho dividiu o módulo em `primitives.py` e `detection.py`.
- [x] Mover iluminação, contraste, unsharp e binarização para `quality.py`.
- [x] Consolidar `enhance` em `pipeline.py`, sem lógica de geometria ou qualidade embutida.
- [x] Avaliar a divisão de `geometry.py` apenas se ultrapassar ~200 statements; nesse caso, `primitives.py` e `detection.py`.
- [x] Expor a API pública via `__init__.py` (fachada estável).
- [x] Rodar testes rápidos, golden outputs e checagem de tamanho dos módulos.

### Critérios de aceite

- [x] Nenhum módulo concentra mais de 30% dos statements.
- [x] Sem imports circulares; dependências apontam para `settings`, `io` e tipos compartilhados.
- [x] API pública documentada na fachada.
- [x] Golden outputs passam.
- [x] `better_docimage.py` foi removido; o entry point único é `python -m better_docimage`.

### Riscos

- O núcleo é a parte mais volátil; qualquer mudança de fórmula deve ser tratada como mudança de comportamento e não entrar nesta fase.
- Divisão excessiva de geometria: manter um módulo enquanto o tamanho não justificar.

---

## Fase 4 — Empacotamento, pinagem e CI

**Objetivo:** tornar a instalação e os resultados reprodutíveis.

**Concluída em 2026-11-14.** O `pyproject.toml` passou a ser a fonte única de metadados, pins e configuração do pytest; o `README.md` documenta instalação, uso, API, testes e reprodutibilidade; e o workflow em `.github/workflows/ci.yml` executa a suíte rápida em push/PR e a lenta sob demanda/agendada. Os arquivos `requirements.txt`, `requirements-dev.txt` e `pytest.ini` foram removidos. A instalação limpa com `python -m pip install -e ".[dev]"`, os dois entry points, `pip check`, a suíte rápida (55 testes) e a suíte lenta (18 golden outputs) passaram no ambiente pinado. A primeira execução remota do workflow fica para o push/PR da fase.

### Tarefas

- [x] Criar `pyproject.toml` com metadados, dependências com faixas pinadas, dependências de desenvolvimento e entry point `better-docimage`.
- [x] Consolidar no `pyproject.toml` os pins temporários usados para gerar o baseline na Fase 0.
- [x] Criar `README.md` com instalação, uso, exemplos e links para ADRs/roadmap.
- [x] Configurar CI para `pytest -m fast` em todo push/PR e `pytest -m slow` sob demanda ou em job agendado.
- [x] Verificar instalação em ambiente limpo e execução do entry point.
- [x] Remover `requirements.txt` ou substituí-lo por um lock coerente com `pyproject.toml`.
- [x] Confirmar que os golden outputs são reproduzidos no ambiente pinado.

### Critérios de aceite

- [x] `pip install -e .` em ambiente limpo instala e expõe `better-docimage`.
- [x] `better-docimage --help` funciona.
- [x] Workflow de CI configurado para testes rápidos em push/PR e suíte lenta sob demanda/agendada; os mesmos comandos passaram localmente. A primeira execução remota verde será confirmada no PR da fase.
- [x] Versões de dependências reproduzem o baseline.
- [x] README permite que uma pessoa nova rode o projeto sem ler o código.

---

## Mapa: achado → decisão → fase

| Achado da análise | ADR | Fase |
|---|---|---|
| Invariante de coordenadas escondida | 003 | 1 |
| Vocabulário de modos duplicado | 002 | 1 |
| Contratos por tupla posicional | 002 | 1 |
| Binário inferido por pixels no I/O | 002, 005 | 1 |
| Validação tardia e inconsistente | 004 | 1 |
| Três convenções de falha / `print` no pipeline | 004 | 1 |
| `Settings` incompleto e constantes espalhadas | 005 | 1 |
| DPI fixo e `quality` ignorado | 005 | 1 |
| Ausência de testes e baseline | 006 | 0 |
| Arquivo único / componentes lógicos | 001 | 2–3 |
| Dependências sem pin e sem entry point | 001, 006 | 0 e 4 |

## Critérios de aceite globais

- [x] Saída preservada nos 18 golden outputs dentro da tolerância documentada.
- [x] Nenhum contrato implícito (dicionário de modos, tupla de dimensões, offset sem tipo) nas fronteiras.
- [x] Toda validação de CLI ocorre antes de I/O; erros de uso não produzem traceback.
- [x] `logging` substitui `print` em código de biblioteca.
- [x] Cada parâmetro de tuning tem uma única fonte de verdade.
- [x] Pacote com 6–7 módulos, sem módulo acima de 30% dos statements e sem imports circulares.
- [ ] Testes unitários e golden outputs rodando em CI. O workflow está pronto; a primeira execução remota ocorre no push/PR.
- [x] Instalação limpa, dependências pinadas e entry point funcionando.
- [x] ADRs e README atualizados.

## Riscos e mitigação

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Regressão visual silenciosa | Média | Alto | Golden outputs + tolerância + revisão visual das miniaturas |
| Over-decomposition | Média | Médio | Limite de 6–7 módulos e ~200 statements para geometria |
| Variação de OpenCV entre plataformas | Média | Médio | Pinagem, tolerância perceptual e hash só no mesmo ambiente |
| Suíte lenta por denoise | Alta | Médio | Fixtures sintéticas pequenas, marker `slow`, baseline gerado uma vez |
| Escopo crescer para "melhorar o algoritmo" | Alta | Médio | Fora de escopo explícito; qualquer mudança de qualidade exige ADR própria |
| Quebra de API para consumidores externos | Baixa | Médio | Fachada em `__init__.py`; não há consumidores conhecidos no repositório |

## Rollback

- Cada fase é um commit/PR independente, com tag antes da fase seguinte.
- O wrapper original permaneceu disponível até o fim da Fase 3 e foi removido ao final dela.
- Golden outputs e hashes permitem comparar qualquer versão com o baseline.
- Nenhuma fase envolve migração de dados ou mudança irreversível.

## Métricas de sucesso

| Métrica | Antes | Depois da Fase 4 | Meta |
|---|---|---|---|
| Módulos de código | 1 | 7 | 6–7 |
| Maior componente lógico | 37% | 27,8% (`detection.py`) | ≤ 30% |
| Edições para adicionar um modo | 4 | 1 (`OutputMode`) | 1 |
| Tempo até erro de argumento inválido | após processamento | antes de I/O | antes de I/O |
| Testes automatizados | 0 | 55 rápidos + 1 lento (18 golden outputs) | Unitários + 18 golden outputs |
| `print` em código de biblioteca | 1 | 0 | 0 |
| Fontes de verdade para tuning | 6+ funções | 1 (`settings.py`) | 1 (`settings.py`) |
| DPI de saída | fixo em 300 | derivado de `target_width` | derivado de `target_width` |
| Entry point instalável | não existia | `better-docimage` | `better-docimage` |
| Instalação reprodutível | não pinada | `pyproject.toml` com pins exatos; sem `requirements.txt` | `pyproject.toml` com pins exatos |
| CI | não existia | fast em push/PR; slow sob demanda/agendada | fast em push/PR; slow documentada |

## Próximos passos

1. [x] Executar a Fase 4: `pyproject.toml`, README, CI e verificação em ambiente limpo.
2. Fazer push da branch da Fase 4, abrir o PR referenciando a ADR-006 e confirmar a primeira execução remota do CI.
3. Fechar o critério global de CI depois do primeiro workflow verde e, se desejado, provisionar os assets para a suíte lenta no job agendado.
