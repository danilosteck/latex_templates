# LaTeX templates

Copy a template folder into your project, edit `main.tex`, compile.

## ABNT (`abnt/`)

Requires TeX Live with `abntex2` (already common on Manjaro/Arch via `texlive-latexextra`).

| Template | Use for |
|---|---|
| `abnt/artigo` | Scientific article (NBR 6022) |
| `abnt/tese` | Thesis, dissertation, TCC (NBR 14724) |

```bash
cp -r ~/Documents/Estudo/tools/latex_templates/abnt/artigo ~/path/to/meu-artigo
cd ~/path/to/meu-artigo
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Same for `tese`. In `main.tex`, fill in `\universidade`, `\disciplina`, `\professor`, `\estudante`, `\matricula`, plus title and the other placeholders. Add citations to `refs.bib`.

Body text is Times New Roman, 12pt, 1.5 line spacing, 1.25 cm first-line indent, justified, with ABNT margins (3 cm top/left, 2 cm bottom/right). Long quotations (`citacao`), footnotes, and page numbers are 10pt; quotations and references use single spacing. To switch the body font to Arial, follow the TIMES/ARIAL comments in `main.tex`.
