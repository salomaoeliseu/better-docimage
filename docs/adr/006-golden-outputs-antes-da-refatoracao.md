# ADR-006: Congelar o comportamento com golden outputs antes da refatoração

- **Data**: 2026-11-13
- **Status**: Aceito
- **Decisores**: Mantenedor do projeto
- **Tags**: testes, regressão, qualidade, CI

## Contexto e problema

Não existem testes automatizados. O projeto é um pipeline de visão computacional com muitos heurísticos (Hough, Otsu, deskew, denoise) e dependências não pinadas: o `.venv` tem OpenCV 5.0.0, NumPy 2.5.4 e Pillow 13.0.0, mas `requirements.txt` não fixa versões. Uma refatoração estrutural pode alterar ordem de operações, interpoladores ou parâmetros e produzir imagens piores sem falhar em nenhum teste.

Há três imagens de entrada em `assets/` que podem servir de baseline, mas não há registro do resultado atual. Sem baseline, "melhorar a estrutura" e "piorar a saída" ficam indistinguíveis.

## Drivers de decisão

- Detectar regressões visuais durante a extração de módulos.
- Permitir refatorar sem alterar a lógica de imagem.
- Manter o custo de CI aceitável e os fixtures pequenos.
- Funcionar em ambientes diferentes, onde OpenCV pode variar levemente.

## Opções consideradas

1. **Não criar testes e confiar em inspeção manual.** Rejeitada: não escala e não cobre regressões sutis.
2. **Comparação byte a byte com saídas completas.** Detecta qualquer mudança, mas é frágil entre plataformas e versões de OpenCV, e os arquivos são grandes.
3. **Camadas: testes unitários exatos + golden outputs com tolerância perceptual e hash por ambiente.** Escolhida.

## Decisão

Antes de mover qualquer arquivo:

1. Gerar as saídas atuais da versão em `better_docimage_refactored.py` para as três imagens de `assets/`, nos modos `color`, `gray` e `bw`, com e sem `--pdf`.
2. Armazenar em `tests/golden/`:
   - hash SHA-256 da saída completa;
   - dimensões e estatísticas (média, p1, p99);
   - miniatura reduzida (lado maior de 600 px) para comparação visual e perceptual.
   Não versionar as imagens completas.
3. Testes unitários exatos, com `np.allclose` ou igualdade:
   - composição de matrizes (`fine_rotation @ crop_matrix @ geometry`);
   - conversão de cantos em `prepare_input`;
   - uma única chamada a `warpPerspective` no caminho final;
   - dimensões de saída para uma largura alvo;
   - parsing e validação da CLI.
4. Testes de regressão com tolerância:
   - miniaturas comparadas por diferença média absoluta e/ou SSIM;
   - limites iniciais sugeridos: diferença média ≤ 1/255 e máximo ≤ 2 níveis, calibrados na Fase 0 com o ambiente pinado;
   - imagem completa comparada por hash apenas quando as versões de dependências forem idênticas.
5. CI executa testes rápidos em todo commit e a suíte de golden outputs em jobs separados ou sob marker `slow`.
6. Qualquer mudança de comportamento intencional exige atualização explícita do golden e justificativa no commit.

## Consequências

### Positivas

- Rede de segurança para as fases de extração e mudança de contratos.
- Regressões localizadas por etapa (geometria, qualidade, I/O).
- Baseline objetivo para comparar algoritmos futuros.
- Fixtures pequenos e CI viável.

### Negativas

- Golden outputs exigem manutenção e revisão quando o comportamento muda de propósito.
- Tolerâncias podem mascarar diferenças pequenas ou gerar falsos positivos entre plataformas.
- A suíte lenta depende de versões pinadas para ser significativa.
- As imagens de teste não cobrem todos os casos (documento sem tabela, cantos manuais, página em branco); casos sintéticos precisam complementar.

## Links

- [ADR-001: Pacote modular por responsabilidade](001-pacote-modular-por-responsabilidade.md)
- [ADR-003: Espaço de coordenadas dos cantos](003-espaco-de-coordenadas-dos-cantos.md)
- [ADR-004: Validação antecipada e política de erros](004-validacao-antecipada-e-politica-de-erros.md)
- [Roadmap de refatoração](../roadmap-refatoracao.md)
