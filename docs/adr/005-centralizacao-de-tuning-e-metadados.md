# ADR-005: Centralizar parâmetros de tuning e metadados de saída

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: arquitetura, configuração, qualidade de imagem, I/O

## Contexto e problema

`Settings` (`better_docimage_refactored.py:41-47`) expõe cinco parâmetros, mas os valores que realmente controlam o resultado estão espalhados pelo código:

- `adaptiveThreshold` 31/12 e 31/15 (`:170-177`, `:277-284`);
- Hough 150/25/8 (`:127-134`);
- escala 1000, passos 0.5 e 0.05 (`:268`, `:300-302`);
- percentis 0.5/90 (`:423-424`);
- sigma 1.6 fixo no `enhance` (`:483`);
- janelas 7/21 do denoise (`:471`);
- `white=252` e `min_ratio=0.02` (`:87-88`);
- DPI 300 (`:66`, `:72`, `:79`).

Ajustar um heurístico exige caçar números em seis funções, e parâmetros semelhantes aparecem com valores diferentes sem justificativa registrada. Além disso, o DPI é fixo em 300 mesmo quando `--width` muda, então o metadado físico do PNG/PDF pode ficar incorreto. O argumento `quality=92` em `save_pdf` (`:72`) é ignorado pelo plugin de PDF do Pillow 13 (verificado no fonte da versão instalada).

## Drivers de decisão

- Uma única fonte de verdade para cada parâmetro.
- Preservar a separação entre configuração do usuário e constantes internas.
- Manter `Settings` imutável e testável.
- Corrigir metadados de resolução sem alterar pixels.

## Opções consideradas

1. **Manter constantes nos corpos das funções.** Menor esforço, mas perpetua a dispersão e a divergência de valores.
2. **Expor todos os parâmetros na CLI.** Centraliza, mas transforma a interface em um painel de tuning e aumenta a superfície de erro.
3. **Agrupar parâmetros internos em dataclasses por etapa, mantendo na CLI apenas os controles de usuário.** Escolhida.

## Decisão

- `Settings` continua sendo a configuração do usuário: `target_width`, `gamma`, `sharpen_amount`, `denoise_strength`, `bw_offset`. Permanece `frozen`.
- Criar `DetectionParams`, `QualityParams` e `IoParams` como dataclasses `frozen` em `settings.py`, com defaults documentados. O pipeline recebe uma instância por etapa; funções de biblioteca não leem constantes globais.
- Cada constante recebe nome, unidade e comentário curto. Valores que precisam ser idênticos entre funções (por exemplo, os parâmetros do `adaptiveThreshold`) tornam-se um único campo reutilizado.
- O DPI de saída é derivado da largura alvo: `dpi = target_width / A4_WIDTH_IN`, com `A4_WIDTH_IN = 8.27`. PNG e PDF usam o mesmo valor.
- `io.py` centraliza a conversão para PIL e a decisão de modo binário; `quality=92` é removido ou substituído por um encoder que realmente aplique qualidade.
- Nenhum parâmetro interno novo é exposto na CLI sem um caso de uso concreto.

## Consequências

### Positivas

- Ajustar um heurístico passa a ser uma edição em um único arquivo.
- Defaults ficam auditáveis e podem ser pinados pelos testes de regressão.
- Metadados de resolução deixam de mentir quando `--width` difere de 300 DPI.
- Remove um argumento morto (`quality`) que dava falsa sensação de controle.

### Negativas

- Mais um objeto de configuração para passar entre funções.
- A calibração inicial exige comparar os valores atuais com os novos defaults para garantir equivalência.
- Dataclasses de tuning podem virar um "grab bag" se não houver critério por etapa; a regra é uma dataclass por estágio do pipeline.

## Links

- [ADR-002: Contratos explícitos nas fronteiras](002-contratos-explicitos-nas-fronteiras.md)
- [ADR-006: Golden outputs antes da refatoração](006-golden-outputs-antes-da-refatoracao.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
