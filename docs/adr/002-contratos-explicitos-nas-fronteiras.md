# ADR-002: Substituir contratos implícitos por tipos explícitos nas fronteiras

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: arquitetura, contratos, tipos, manutenibilidade

## Contexto e problema

As fronteiras entre as etapas do pipeline usam estruturas implícitas:

- `enhance` retorna `dict[str, np.ndarray]` com as chaves `"color"`, `"gray"` e `"bw"` (`better_docimage_refactored.py:486-490`).
- O vocabulário dos modos aparece em quatro lugares: chaves do dicionário, default `"color,gray"` (`:517`), texto de ajuda (`:518`) e `valid_modes` (`:550`). Um modo novo exige quatro edições coordenadas; um erro de digitação gera `KeyError` depois do processamento caro.
- `table_geometry_transform`, `perspective_transform` e `build_combined_transform` retornam `tuple[np.ndarray, tuple[int, int]]` (`:165`, `:224`, `:313`). A ordem `(width, height)` é posicional e não é verificável por type checker.
- O offset de recorte é uma tupla `(x, y)` sem tipo próprio.
- `save_png` e `save_pdf` inferem que uma imagem é binária varrendo os pixels com `set(np.unique(img)) <= {0, 255}` (`:64`, `:77`). O conhecimento "esta saída é binária" existe em `enhance`, mas é redescoberto por inspeção de dados no I/O.

Esses são acoplamentos de modelo e funcionais simétricos. Com distância baixa (mesmo arquivo), o custo é local; após a extração prevista na ADR-001, passariam a ser caros.

## Drivers de decisão

- Eliminar edições sincronizadas e erros de digitação em strings.
- Tornar a ordem e a semântica dos dados verificáveis pelo interpretador e pelo type checker.
- Levar a semântica da imagem (colorida, cinza ou binária) junto com os dados.
- Manter o custo de mudança baixo sem introduzir um framework.

## Opções consideradas

1. **Manter dicionário e constantes de string.** Simples, mas mantém a connascência de posição e a duplicação.
2. **Usar `TypedDict` e `NamedTuple`.** Melhora a checagem estática, porém não impede acessos por chave arbitrária em runtime e mantém a semântica de tupla.
3. **Usar dataclasses `frozen` e `Enum`.** Escolhida: acesso por nome, imutabilidade, igualdade estrutural e tipos verificáveis.

## Decisão

Introduzir contratos explícitos nas fronteiras:

| Hoje | Novo contrato |
|---|---|
| `dict[str, np.ndarray]` + strings de modo | `OutputMode` (enum) + `EnhancementResult` |
| `tuple[ndarray, tuple[int, int]]` | `TransformPlan(transform: ndarray, size: Size)` |
| `tuple[int, int]` para offset | `Offset(x: int, y: int)` |
| Inspeção de pixels para binário | `RenderedImage(data: ndarray, is_binary: bool)` |

Regras:

- `OutputMode` é a única fonte de verdade para `color`, `gray` e `bw`. O argparse deriva `choices` do enum.
- `EnhancementResult` expõe os modos solicitados; `enhance` calcula apenas o que foi pedido, em vez de sempre gerar `gray` e `bw`.
- `Size` nomeia `width` e `height`; nenhuma função retorna tupla posicional de dimensões.
- `RenderedImage` carrega `is_binary` desde o pipeline; `io.py` não infere semântica varrendo a matriz.
- Os tipos são `@dataclass(frozen=True)` para permitir uso como valor e evitar mutação acidental.

## Consequências

### Positivas

- Adicionar um modo passa a ser uma edição no enum, não quatro.
- Trocar largura por altura deixa de compilar silenciosamente.
- O I/O deixa de fazer uma varredura O(n log n) sobre milhões de pixels apenas para descobrir se a imagem é binária.
- Testes de contrato podem verificar os tipos e os modos sem depender da CLI.

### Negativas

- Pequeno boilerplate de dataclasses e enums.
- `EnhancementResult` precisa de uma representação que acomode modos opcionais sem voltar ao dicionário; a proposta é um campo por modo, com `None` quando não solicitado.
- Chamadas internas precisam ser atualizadas de uma vez; a fachada pública deve ser mantida durante a migração.

## Links

- [ADR-001: Pacote modular por responsabilidade](001-pacote-modular-por-responsabilidade.md)
- [ADR-003: Espaço de coordenadas dos cantos](003-espaco-de-coordenadas-dos-cantos.md)
- [ADR-005: Centralização de tuning e metadados](005-centralizacao-de-tuning-e-metadados.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
