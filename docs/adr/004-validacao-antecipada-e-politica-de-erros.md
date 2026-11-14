# ADR-004: Validar entradas antes do processamento e unificar a política de erros

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: arquitetura, CLI, tratamento de erros, observabilidade

## Contexto e problema

A CLI e o pipeline tratam falhas de três maneiras diferentes:

- `--modes` só é validado depois de `load_image` e `enhance` (`better_docimage_refactored.py:546-554`). Um erro de digitação faz o usuário esperar todo o processamento para receber a mensagem.
- `parse_corners` lança `ValueError` (`:499-505`) sem tratamento, produzindo traceback, enquanto os demais erros de argumento usam `parser.error`.
- `--modes ""` não gera arquivo algum e termina com código 0, sem aviso.
- `--sharpen` negativo é aceito e desliga o sharpen silenciosamente (`:431-432`).
- Funções de detecção retornam `None` (`:191`, `:211`, `:241`), configurações inválidas lançam exceção (`:384`, `:419`) e o fallback imprime `"aviso: ..."` em stdout (`:335`). O `None` mistura "não detectado", "matriz singular" e "grande demais", então a qualidade pode cair sem explicação.
- `print` dentro do pipeline polui a saída e não pode ser controlado por nível.

## Drivers de decisão

- Falhar antes de qualquer I/O ou processamento caro.
- Mensagens de erro acionáveis, sem traceback para erro de uso.
- Diagnóstico de fallbacks sem poluir stdout.
- Distinguir ausência esperada de erro de programação ou configuração.

## Opções consideradas

1. **Manter o comportamento atual.** Simples, mas repete o custo de validação tardia e as três convenções de falha.
2. **Lançar exceções em todos os casos.** Consistente, porém transforma "documento sem linhas detectáveis", que é esperado, em erro fatal.
3. **Política híbrida: validação na borda, `None` documentado para ausência esperada, exceção para configuração inválida e `logging` para diagnóstico.** Escolhida.

## Decisão

1. Separar `build_parser()` e `run(args)` de `main()`, permitindo testar a CLI sem executar o pipeline.
2. Validar todos os argumentos antes de `load_image`:
   - `--modes` usa `choices` derivado de `OutputMode`; lista vazia é erro; duplicatas são removidas preservando a ordem.
   - `--corners` usa um `type=` que converte e valida os oito valores, levantando `argparse.ArgumentTypeError`.
   - `--sharpen >= 0`, `--denoise >= 0`, `--gamma > 0`, `--width > 0` são checados em um único ponto.
3. Política de falhas do domínio:
   - **Ausência esperada** (sem linhas, sem tabela, perspectiva inválida) → `None`, documentado por função.
   - **Configuração ou invariante inválida** → exceção com mensagem específica.
   - **Diagnóstico e fallback** → `logging` em stderr; `--verbose` controla o nível. Nada de `print` no pipeline.
4. O fallback registra o motivo: por exemplo, "perspectiva inválida; usando detecção de tabela", em vez de apenas seguir adiante.
5. Erros de uso terminam com código 2 e mensagem curta; erros de execução com código 1 e log.

## Consequências

### Positivas

- Erros de digitação são detectados em milissegundos, não após minutos de denoise.
- Sem traceback para erro de uso; sem saída inesperada em stdout.
- Quando a qualidade cair, o log explica qual detector falhou e qual fallback foi usado.
- A CLI fica testável e o pipeline independente de `argparse`.

### Negativas

- Mais código de validação e de logging.
- A distinção entre "ausência esperada" e "erro" exige critério por função e revisão nos testes.
- Usuários que dependiam de `print` em stdout precisam se adaptar ao stderr.

## Links

- [ADR-002: Contratos explícitos nas fronteiras](002-contratos-explicitos-nas-fronteiras.md)
- [ADR-006: Golden outputs antes da refatoração](006-golden-outputs-antes-da-refatoracao.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
