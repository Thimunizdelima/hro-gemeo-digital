# 🏥 HRO Gêmeo Digital — Simulador de Contingência Hospitalar & Prescrição Eletrônica

Plataforma de **Gêmeo Digital Hospitalar (Digital Twin)** desenvolvida em Python (**FastAPI + SQLite + TailwindCSS**) para simulação em tempo real de cenários críticos de contingência, giro de leitos, restrição de recursos humanos, insuficiência de equipamentos de suporte à vida, crise energética/TI e prescrição eletrônica (PEP) 100% anonimizada (LGPD).

---

## 🏛️ Arquitetura Estrutural de Leitos Calibrada (Regra HRO)

- **340 Leitos Fixos de Internação e Terapia Intensiva (`FIXO`):**
  - `UTI-AD` — UTI Geral Adulto (Alas A/B/C/D): **40 leitos**
  - `UTI-PED` — UTI Pediátrica: **10 leitos**
  - `UTI-NEO` — UTI Neonatal & UCINCO: **20 leitos**
  - `CLIN-CIR` — Clínica Cirúrgica & Ortopedia/Trauma: **85 leitos**
  - `CLIN-MED` — Clínica Médica & Neurologia/Cardio: **80 leitos**
  - `ONCO-UNA` — Oncologia Clínica e Cirúrgica (UNACON): **45 leitos**
  - `MAT-OBST` — Maternidade Alto Risco & Alojamento Conjunto: **35 leitos**
  - `PED-CLIN` — Pediatria Clínica: **25 leitos**
- **Pronto-Socorro (`PS-EMERG` — `APOIO_PS`):** Contabilizado separadamente como **leitos de apoio** (45 pontos instalados + 25 macas extras de contingência).
- **Centro Cirúrgico & SRPA (`CC-SRPA` — `APOIO_SRPA`):** **18 leitos fixos de SRPA** + 10 salas cirúrgicas.

---

## 🚨 Cenários de Simulação de Contingência

1. **Controle de Efetivo de Ocupação e Áreas Críticas:** Ajuste fino por setor ou via multiplicador global de censo com geração/remoção dinâmica de pacientes anonimizados (`PAC-HRO-XXXX`) e prescrições.
2. **Superlotação do Centro Cirúrgico / SRPA (18 Leitos) & *ICU Exit Block*:** Simula cirurgias leito-dependentes retidas na SRPA e salas cirúrgicas travadas por falta de vaga na `UTI-AD` (40/40), enquanto pacientes com alta médica da UTI ficam retidos por falta de leitos nas enfermarias (`CLIN-CIR` e `CLIN-MED`).
3. **Falta de Monitores Multiparamétricos, Ventiladores Mecânicos e Quantitativo Insuficiente:** Simula indisponibilidade técnica e déficit frente à demanda assistencial em UTIs, SRPA, PS e Enfermarias.
4. **Falta de Energia por Tempo Indeterminado + Falha de Geradores:** Calcula autonomia restante de baterias internas de Ventiladores Mecânicos (90 min) e Bombas de Infusão (120 min), demanda de Ambu 1:1 e insere alertas nas prescrições de pacientes eletrodependentes.
5. **Queda do Sistema Informatizado sem Previsão de Retorno (Modo Papel):** Simula apagão de PEP/HIS/PACS/LIS com transição para formulários físicos carbonados, cálculo de prescrições acumuladas para conciliação e sobrecarga de enfermagem.
6. **Ruptura Farmacêutica & Substituição Terapêutica Automática (CFT):** Identifica prescrições afetadas por falta de medicamentos vitais e aplica substituição padronizada em 1 clique.
7. **Incidente com Múltiplas Vítimas (IMV — Protocolo START) & Restrição de RH (COFEN / RDC-7).**

---

## 📚 Motor de Decisões Baseadas em Evidências Científicas

Inclui aba dedicada com classificação dinâmica **NAM/IOM *Crisis Standards of Care*** (*Conventional*, *Contingency* e *Crisis Care*), **Matriz 4S (*Space, Staff, Stuff, System* — Hick et al. / CHEST)** e **10 protocolos científicos executáveis com 1 clique**:

- **Fluxo Puxado (*Pull System*) + *Discharge Lounge* + Giro UTI < 45 min** (*Goldfrad & Rowan / Lean nas Emergências PROADI-SUS*)
- **Suavização do Mapa Cirúrgico (*Surgical Smoothing*)** (*Litvak et al. / IHO*)
- ***Full Capacity Protocol* (+2 leitos/ala)** (*Viccellio et al. / Stony Brook / ACEP*)
- **Triagem Reversa (*Reverse Triage*)** (*Kelen et al. / Johns Hopkins*)
- ***Step-Down* de Monitores Guiado por `NEWS2 < 3`** (*Royal College of Physicians / CHEST*)
- **Protocolo CHEST para Escassez de Ventiladores (VNI/CNAFO + Aparelhos de Anestesia)**
- **Substituição Terapêutica Automática (Diretriz ASHP / CFT)**
- **Protocolo ONC SAFER Guides (Contingência Offline & Conciliação de TI)**
- **Protocolo NFPA 99 / OMS Hospital Safety Index (Barramento Crítico & O2)**
- ***Functional Team Nursing* & Remanejamento Assistencial (COFEN 543/2017 / RDC-7)**

---

## 🚀 Como Executar Localmente

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8090
```

Acesse no navegador: **`http://127.0.0.1:8090`**

---

## ☁️ Deploy em Nuvem (Render / Docker)

O repositório já inclui [`Dockerfile`](Dockerfile) e [`render.yaml`](render.yaml) configurados para deploy imediato via Docker ou Blueprint no Render.
