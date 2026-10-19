# BibTeX Entry Skeleton

> Copy the block matching the source type. Replace `P-XXXX` with the paper ID (the
> cite key), fill fields from `papers/P-XXXX.md`, then delete unused optional fields.
> Rules: cite key = paper ID; protect capitalisation with `{…}`; escape `& % $ # _`;
> keep field order author, title, journal/booktitle, year, volume, number, pages,
> publisher, doi, url.

## @article — journal article

```bibtex
@article{P-XXXX,
  author  = {Last, First and Last, First},
  title   = {{Exact Title With Protected Acronyms}},
  journal = {Journal Name},
  year    = {YYYY},
  volume  = {VV},
  number  = {NN},
  pages   = {PP--PP},
  doi     = {10.xxxx/xxxxx},
  url     = {https://...}
}
```

## @inproceedings — conference paper

```bibtex
@inproceedings{P-XXXX,
  author    = {Last, First and Last, First},
  title     = {{Title}},
  booktitle = {Proceedings of ...},
  year      = {YYYY},
  pages     = {PP--PP},
  publisher = {Publisher},
  doi       = {10.xxxx/xxxxx},
  url       = {https://...}
}
```

## @incollection — book chapter

```bibtex
@incollection{P-XXXX,
  author    = {Last, First},
  title     = {{Chapter Title}},
  booktitle = {Book Title},
  editor    = {Last, First},
  publisher = {Publisher},
  year      = {YYYY},
  pages     = {PP--PP},
  doi       = {10.xxxx/xxxxx}
}
```

## @book — book

```bibtex
@book{P-XXXX,
  author    = {Last, First},
  title     = {{Book Title}},
  publisher = {Publisher},
  year      = {YYYY},
  address   = {City},
  doi       = {10.xxxx/xxxxx}
}
```

## @misc — preprint or web page

```bibtex
@misc{P-XXXX,
  author       = {Last, First},
  title        = {{Title}},
  year         = {YYYY},
  howpublished = {arXiv / preprint / web},
  eprint       = {XXXX.XXXXX},
  url          = {https://...},
  note         = {Accessed: YYYY-MM-DD}
}
```

## @techreport — grey literature / report

```bibtex
@techreport{P-XXXX,
  author      = {{World Health Organization}},
  title       = {{Report Title}},
  institution = {Institution Name},
  year        = {YYYY},
  number      = {Report Number},
  url         = {https://...}
}
```

## @phdthesis / @mastersthesis — thesis

```bibtex
@phdthesis{P-XXXX,
  author = {Last, First},
  title  = {{Thesis Title}},
  school = {University Name},
  year   = {YYYY},
  url    = {https://...}
}
```
