# Slide Generation Agent

Paper PDF in, .pptx out (Google ADK).

```
Agent/
├─ slide_agent/        ADK app (adk web / adk run target)
│  ├─ agent.py         root_agent
│  ├─ config.py        .env, paths, per-agent model (OpenRouter via LiteLlm)
│  ├─ schemas.py       Asset / SlideSpec / Outline
│  ├─ agents/          sub-agents (none yet)
│  ├─ tools/
│  │  └─ asset_extractor/   논문 PDF에서 그림/표/알고리즘/수식을 PNG로 자르는 도구 (아래 설명)
│  └─ prompts/         <agent>.md
├─ tests/              pytest (asset_extractor)
├─ eval/               comparison with ../examples/*/slides.pdf
└─ outputs/            generated decks and crops (git-ignored)
```

Setup:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in OPENROUTER_API_KEY
adk web
```

Reference data (paper.pdf + slides.pdf pairs) lives in `../examples/`.

## asset_extractor: 논문 PDF에서 그림/표/알고리즘/수식 자르기

LLM을 쓰지 않는 순수 Python 도구(PyMuPDF)입니다. 논문 PDF 하나를 받아서, 슬라이드에 재사용할 수 있는 자료를 PNG로 잘라 저장하고 목록(`assets.json`)을 만듭니다.

자르는 대상:

| kind | 찾는 방법 |
|---|---|
| `figure`, `table` | "Figure 2." / "Table 1:" 캡션 옆의 그래픽과 작은 글씨(축 라벨, 표 셀)를 묶음 |
| `algorithm` | 캡션 근처의 가로선으로 둘러싸인 박스 (제목이 박스 안에 있으면 제목 포함) |
| `equation` | 단 오른쪽 끝의 번호 `(3)`이 붙은 별도 수식 (본문 중간의 인라인 수식은 제외) |

캡션 글자는 이미지에 넣지 않고 `assets.json`의 `caption`에 텍스트로 저장합니다(알고리즘 제목은 예외). 부록(References 뒤)의 자료도 포함하되 `in_appendix: true`로 표시합니다.

### 터미널에서 실행

`Agent` 폴더에서 venv를 켠 상태로 실행합니다.

```
python -m slide_agent.tools.asset_extractor ..\examples\CVPR2023_20941_8wm5267\paper.pdf --sheet
```

결과는 `outputs/<시각>_<pdf 파일명>/`에 저장됩니다. 옵션:

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--out DIR` | `outputs/<시각>_<pdf 이름>` | 저장 폴더 (이미 있으면 같은 이름의 파일을 덮어씀) |
| `--kinds ...` | 전부 | `figure table algorithm equation` 중 자를 종류 |
| `--no-appendix` | 부록 포함 | 부록의 자료 제외 |
| `--dpi N` | 300 | PNG 해상도 (높을수록 선명하고 파일이 큼) |
| `--sheet` | 꺼짐 | `preview_N.jpg`(자른 이미지 12개씩 모은 미리보기) 추가 생성 |

예: 그림과 표만, 150dpi로

```
python -m slide_agent.tools.asset_extractor paper.pdf --kinds figure table --dpi 150
```

### 파이썬 코드에서 호출

```python
from slide_agent.tools.asset_extractor import extract_assets

manifest = extract_assets("paper.pdf", "outputs/my_paper", kinds=("figure", "table"), include_appendix=True, dpi=300)
for asset in manifest.assets:
    print(asset.id, asset.page, asset.image_path, asset.caption[:50])
print(manifest.warnings)
```

### 출력 폴더 구조

```
outputs/<시각>_<이름>/
├─ assets/            fig_1.png, tab_1.png, alg_1.png, eq_3.png ...
├─ assets.json        자른 자료 목록 (아래)
└─ preview_1.jpg ...  --sheet를 줬을 때만
```

`assets.json`:

| 필드 | 내용 |
|---|---|
| `pdf`, `num_pages`, `appendix_start_page` | 원본 파일 이름, 쪽 수, 부록이 시작되는 쪽(없으면 null) |
| `settings` | 실행 옵션 (`kinds`, `include_appendix`, `dpi`) |
| `assets[].id` | `fig_2`, `tab_1`, `alg_1`, `eq_3`. 부록에서 번호가 겹치면 `_app` 접미사 |
| `assets[].kind`, `number` | 종류와 논문에 인쇄된 번호 |
| `assets[].page`, `bbox` | 쪽 번호(1부터)와 PDF 좌표 `(x0, y0, x1, y1)`. 같은 PDF로 같은 자리를 다시 자를 수 있음 |
| `assets[].caption` | 캡션 텍스트 (수식은 바로 위 문장) |
| `assets[].image_path`, `size_px` | `assets/` 아래 PNG 경로(출력 폴더 기준)와 픽셀 크기 |
| `assets[].in_appendix` | 부록에 있는 자료인지 |
| `assets[].mentioned_in` | 이 자료를 언급하는 본문 섹션 제목들 |
| `warnings` | 아래 참고 |

### warnings 읽는 법

경고가 있어도 나머지 결과는 정상 저장됩니다. 사람이 확인해야 할 신호입니다.

- `... caption found but no graphic next to it`: 캡션은 찾았는데 옆에서 그림/표를 못 찾음
- `... is mentioned in the text but was not extracted`: 본문에서 언급되는데 못 자름 (부록이 PDF에 없는 경우도 흔함)
- `Equation numbers not found in the main text: [3, 4]`: 수식 번호가 중간에 비어 있음

### 논문 여러 편을 한 번에

`examples/` 아래 모든 논문에 돌리고 논문별 개수와 경고를 `summary.json`으로 모읍니다. 추출기를 고친 뒤 다른 논문이 깨지지 않았는지 비교할 때 씁니다.

```
python ..\scripts\extract_all.py [--dpi 300] [--out DIR]
```

결과는 `outputs/<시각>_all_examples/<논문 폴더 이름>/`에 저장됩니다.

### 코드 구조 (`slide_agent/tools/asset_extractor/`)

위에서 아래 순서로 읽으면 흐름이 이어집니다.

| 파일 | 역할 |
|---|---|
| `page_content.py` | PDF를 줄/그래픽/단 정보로 읽음. 머리글·바닥글 판정 |
| `captions.py` | `Figure 2.` 같은 캡션을 찾음 |
| `regions.py` | 캡션 옆의 그림/표/알고리즘 영역을 찾음 |
| `equations.py` | 번호 붙은 수식을 찾음 |
| `sections.py` | 부록 시작 위치, 각 자료를 언급하는 섹션 |
| `extractor.py` | 위를 엮어서 PNG로 자르고 `assets.json`을 씀 (`extract_assets`) |
| `preview.py`, `__main__.py` | 미리보기 시트, 터미널 실행 |

### 테스트

```
python -m pytest -q
```

정규식과 id 규칙 같은 단위 테스트, 그리고 `../examples/`의 논문 몇 편으로 개수, 파일 존재, bbox 범위를 확인하는 테스트가 있습니다. 예시 논문이 없으면 해당 테스트는 건너뜁니다.

### 알려진 한계

- 그림 안의 하위 그림(a), (b)는 따로 자르지 않고 하나로 자릅니다.
- 위/아래로 붙은 자료, 나란히 놓인 자료는 규칙으로 나누는데 틀릴 수 있습니다. 예시 153편 중 아직 같은 영역을 두 자료가 잡는 경우가 2건 있습니다.
- 수식의 글자 위치가 부정확한 PDF에서는 수식 가장자리가 조금 잘리거나 위 문단 한 줄이 섞일 수 있습니다.
- 스캔본(글자가 없는 PDF)과 본문 줄을 못 찾는 PDF(`CVPR2023_21504`)는 오류가 납니다.
- 판정 기준값(허용 간격 등)은 예시 논문에 맞춰 정한 값이라 새로운 양식의 논문에서는 안 맞을 수 있습니다.
