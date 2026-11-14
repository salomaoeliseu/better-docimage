# Architecture Decision Records — Better-DocImage

Este diretório registra as decisões arquiteturais da refatoração estrutural do projeto. O contexto completo, os achados e a ordem de execução estão no [roadmap de refatoração](../roadmap-refatoracao.md).

## Índice

| ADR | Decisão | Status | Data |
|---|---|---|---|
| [ADR-001](001-pacote-modular-por-responsabilidade.md) | Extrair o script em pacote modular por responsabilidade | Aceito | 2026-11-13 |
| [ADR-002](002-contratos-explicitos-nas-fronteiras.md) | Substituir contratos implícitos por tipos explícitos | Aceito | 2026-11-13 |
| [ADR-003](003-espaco-de-coordenadas-dos-cantos.md) | Formalizar o espaço de coordenadas dos cantos e do recorte | Aceito | 2026-11-13 |
| [ADR-004](004-validacao-antecipada-e-politica-de-erros.md) | Validar entradas antes do processamento e unificar erros | Aceito | 2026-11-13 |
| [ADR-005](005-centralizacao-de-tuning-e-metadados.md) | Centralizar tuning e metadados de saída | Aceito | 2026-11-13 |
| [ADR-006](006-golden-outputs-antes-da-refatoracao.md) | Congelar comportamento com golden outputs | Aceito | 2026-11-13 |

## Contexto

O projeto começou como um script único de 565 linhas (`better_docimage_refactored.py`) com sete componentes lógicos: CLI, I/O, recorte, detecção geométrica, composição de transformações, qualidade de imagem e orquestração. A análise de acoplamento concluiu que o código é coeso no estado atual, mas que os contratos implícitos entre etapas encareceriam a manutenção assim que os módulos fossem separados. As ADRs registram as decisões que orientam essa separação.

## Convenções

- ADRs são registros históricos: uma decisão não é editada; ela é substituída por uma nova ADR.
- O número é sequencial e o nome do arquivo segue `NNN-kebab-case.md`.
- Toda ADR tem data, status, contexto, decisão, consequências (positivas e negativas) e links.
- Decisões de implementação que não alteram a arquitetura devem ficar no roadmap ou no PR, não em uma ADR.

## Como criar uma nova ADR

1. Verifique o maior número neste diretório.
2. Crie `NNN-titulo-em-kebab-case.md` com o template MADR.
3. Adicione a entrada na tabela acima.
4. Se a nova decisão substituir uma anterior, atualize o status da antiga para `Substituído por ADR-NNN` e linke nos dois sentidos.
