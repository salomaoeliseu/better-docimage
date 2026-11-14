# ADR-003: Formalizar o espaço de coordenadas dos cantos e a invariante de recorte

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: arquitetura, correção, geometria, coordenadas

## Contexto e problema

Os cantos informados em `--corners` são definidos na imagem original, antes do recorte de margens. O fluxo atual é:

1. `enhance` recorta a imagem com `trim_blank_border_with_offset` (`better_docimage_refactored.py:459`).
2. `build_combined_transform` recebe `original_crop_offset` e subtrai o offset dos cantos (`:325-330`).
3. O resultado da perspectiva é usado como se os cantos já estivessem no espaço da imagem recortada.

A ordem das operações e o espaço de coordenadas existem apenas em comentário e docstring. Se alguém reordenar as chamadas, mover o recorte ou passar cantos já ajustados, o resultado é **silenciosamente errado** — não há exceção. A força do acoplamento é alta (funcional sequencial + connascência de significado), a volatilidade é alta (núcleo) e a distância é baixa apenas porque tudo está no mesmo arquivo.

## Drivers de decisão

- Tornar impossível usar cantos no espaço errado.
- Concentrar a conversão de coordenadas em um único ponto.
- Preservar a assinatura pública atual durante a migração.
- Permitir teste direto da conversão, sem processar uma imagem inteira.

## Opções consideradas

1. **Manter `original_crop_offset` como parâmetro.** Funciona, mas mantém a armadilha: o chamador precisa lembrar de subtrair o offset.
2. **Mover o recorte para dentro de `build_combined_transform`.** Reduz um parâmetro, mas mistura preparação de entrada com estimativa geométrica e dificulta reutilização.
3. **Criar uma etapa explícita de preparação que devolve imagem e cantos no mesmo espaço.** Escolhida.

## Decisão

Introduzir uma etapa de preparação com um contrato único:

```python
@dataclass(frozen=True)
class PreparedInput:
    image: np.ndarray
    corners: np.ndarray | None   # sempre no espaço de `image`
    crop: Offset                 # offset aplicado à imagem original

def prepare_input(source: np.ndarray, corners: np.ndarray | None) -> PreparedInput:
    image, offset = trim_blank_border_with_offset(source)
    if corners is not None:
        corners = corners - np.asarray(offset, dtype=np.float32)
    return PreparedInput(image=image, corners=corners, crop=Offset(*offset))
```

Regras:

- `build_combined_transform` deixa de receber `original_crop_offset`. Seu parâmetro passa a se chamar `corners_in_input` e a docstring declara que ele está no espaço da imagem recebida.
- A conversão acontece exatamente uma vez, em `prepare_input`.
- `EnhancementResult` ou o pipeline registra o `crop` aplicado, útil para diagnóstico e para mapear coordenadas de volta à origem.
- Testes cobrem: cantos no espaço original, imagem sem margens (offset zero), imagem totalmente branca e cantos fora dos limites após o recorte.

## Consequências

### Positivas

- Elimina a classe de bug de desalinhamento silencioso.
- A assinatura de `build_combined_transform` fica menor e mais honesta.
- A conversão pode ser testada isoladamente com uma imagem sintética pequena.
- Facilita uma futura interface que devolva coordenadas no espaço original.

### Negativas

- Cria mais um tipo (`PreparedInput`) e uma etapa no pipeline.
- Durante a migração, chamadas antigas precisam ser adaptadas de uma vez.
- Se `--corners` for usado com uma imagem já recortada pelo usuário, a semântica continua sendo "coordenadas da imagem de entrada"; isso precisa estar claro na ajuda da CLI.

## Links

- [ADR-001: Pacote modular por responsabilidade](001-pacote-modular-por-responsabilidade.md)
- [ADR-002: Contratos explícitos nas fronteiras](002-contratos-explicitos-nas-fronteiras.md)
- [ADR-006: Golden outputs antes da refatoração](006-golden-outputs-antes-da-refatoracao.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
