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

Same for `tese`. Fill in title, author, and institution placeholders in `main.tex`; add citations to `refs.bib`.
