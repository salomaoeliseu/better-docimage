# ADR-001: Extrair o script em pacote modular por responsabilidade

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: arquitetura, modularização, manutenibilidade

## Contexto e problema

`better_docimage_refactored.py` concentra 19 funções e 254 statements em um único módulo: CLI, I/O, detecção geométrica, composição de transformações, qualidade de imagem, recorte e orquestração. Os banners de seção já delimitam sete componentes lógicos coesos, mas não existem fronteiras físicas nem metadados de pacote.

A análise de acoplamento mostrou que o acoplamento forte atual está próximo (mesmo arquivo), o que é coesão. O risco está na extração ingênua: os contratos entre etapas são implícitos (tuplas posicionais, dicionário de saída, offset de recorte) e passariam de distância baixa para alta sem que a força diminuísse. Além disso, o núcleo (geometria e qualidade) é a parte mais volátil, enquanto CLI e I/O são estáveis.

## Drivers de decisão

- Preservar a invariante de reamostragem única da imagem.
- Isolar o núcleo volátil sem aumentar o custo de mudança.
- Permitir testes unitários por etapa.
- Evitar over-decomposition para um código de aproximadamente 565 linhas.
- Fazer a migração em etapas reversíveis, sem alterar o comportamento observável.

## Opções consideradas

1. **Manter o arquivo único.** Baixo esforço agora, mas mantém contratos implícitos e dificulta testes e evolução.
2. **Dividir imediatamente em muitos módulos por camada técnica.** Aumentaria a distância do acoplamento forte antes de criar contratos, elevando o custo de manutenção.
3. **Extrair um pacote enxuto (6–7 módulos), em etapas, movendo primeiro o que é estável.** Escolhida.

## Decisão

Adotar o pacote `better_docimage` com a seguinte estrutura:

```text
better_docimage/
├── __init__.py        # fachada pública, sem lógica
├── __main__.py        # python -m better_docimage
├── cli.py             # parser, validação, run
├── settings.py        # Settings + parâmetros por etapa
├── io.py              # load/save + RenderedImage
├── pipeline.py        # enhance + OutputMode + EnhancementResult
├── geometry.py        # matrizes, recorte, detecção, composição
└── quality.py         # iluminação, contraste, unsharp, binarize
```

Regras de fronteira:

- `__init__.py` é apenas fachada pública, sem lógica de domínio. Isso evita o padrão de "orphaned classes" na raiz do pacote.
- `geometry.py` só deve ser subdividido (`primitives.py`, `detection.py`) se ultrapassar aproximadamente 200 statements. Para o tamanho atual, um módulo é suficiente.
- A ordem de extração é: contratos e testes → I/O e CLI → geometria e qualidade → empacotamento. Mover primeiro o código estável reduz o risco; o núcleo volátil é movido por último, quando os contratos já estiverem explícitos.
- Nenhum módulo deve concentrar mais de 30% dos statements do código.

## Consequências

### Positivas

- Núcleo volátil isolado e testável sem carregar CLI ou I/O.
- Contratos explícitos nas fronteiras, reduzindo o custo de mudanças futuras.
- Facilita pinagem de dependências, entry point e CI.
- Permite evolução independente de geometria e qualidade.

### Negativas

- Mais arquivos e imports para um projeto pequeno.
- Risco de over-decomposition se a estrutura for seguida sem critério; a regra de 200 statements limita isso.
- Durante a migração, pode haver reexports temporários e duplicação de caminhos de import.
- Exige disciplina para manter a fachada pública estável.

## Links

- [ADR-002: Contratos explícitos nas fronteiras](002-contratos-explicitos-nas-fronteiras.md)
- [ADR-003: Espaço de coordenadas dos cantos](003-espaco-de-coordenadas-dos-cantos.md)
- [ADR-006: Golden outputs antes da refatoração](006-golden-outputs-antes-da-refatoracao.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
