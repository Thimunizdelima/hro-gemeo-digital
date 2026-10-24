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
8. **7 Novos Cenários de Crise (Pontos Cegos Hospitalares & Infraestrutura Vital):**
   - **Queda de Pressão / Congelamento do Tanque VIE de Oxigênio Líquido** (`2,6 kgf/cm²` — Risco de parada de ventiladores nas UTIs).
   - **Pane de Osmose Reversa & Falta de Água na Hemodiálise** (18 pacientes renais retidos sob risco de hipercalemia letal).
   - **Colapso da Agência Transfusional & Esgotamento de Sangue `O Negativo`** (Múltiplos Protocolos de Transfusão Maciça simultâneos).
   - **Pane Total da CME / Autoclaves Inoperantes** (Esgotamento de caixas cirúrgicas estéreis a 18%).
   - **Desastre Químico Agroindustrial (HazMat: Amônia Anidra / Organofosforados)** (+14 vítimas contaminadas no PS e ruptura de Atropina).
   - **Incêndio / Fumaça Tóxica & Evacuação Horizontal de Emergência da UTI Adulto** (10 leitos bloqueados e transferência para SRPA).
   - **Colapso Materno-Neonatal** (`UTI-NEO` em 20/20 leitos + 4 recém-nascidos prematuros extremos intubados retidos no Centro Obstétrico).

---

## 📚 Motor de Decisões Baseadas em Evidências Científicas (16 Protocolos + Monitor 96h)

Inclui aba dedicada com classificação dinâmica **NAM/IOM *Crisis Standards of Care*** (*Conventional*, *Contingency* e *Crisis Care*), **Monitor de Autossuficiência Hospitalar de 96 Horas (*The Joint Commission* `EM.12.02.11`)**, **Matriz 4S (*Space, Staff, Stuff, System* — Hick et al. / CHEST)** e **16 protocolos científicos executáveis com 1 clique**:

1. **Fluxo Puxado (*Pull System*) + *Discharge Lounge* + Giro UTI < 45 min** (*Goldfrad & Rowan / Lean nas Emergências PROADI-SUS*)
2. **Suavização do Mapa Cirúrgico (*Surgical Smoothing*)** (*Litvak et al. / IHO*)
3. ***Full Capacity Protocol* (+2 leitos/ala)** (*Viccellio et al. / Stony Brook / ACEP*)
4. **Triagem Reversa (*Reverse Triage*)** (*Kelen et al. / Johns Hopkins*)
5. ***Step-Down* de Monitores Guiado por `NEWS2 < 3`** (*Royal College of Physicians / CHEST*)
6. **Protocolo CHEST para Escassez de Ventiladores (VNI/CNAFO + Aparelhos de Anestesia)**
7. **Substituição Terapêutica Automática (Diretriz ASHP / CFT)**
8. **Protocolo ONC SAFER Guides (Contingência Offline & Conciliação de TI)**
9. **Protocolo NFPA 99 / OMS Hospital Safety Index (Barramento Crítico & O2)**
10. ***Functional Team Nursing* & Remanejamento Assistencial (COFEN 543/2017 / RDC-7)**
11. **Regra de Autossuficiência de 96h (*Joint Commission*) & Conservação/Descongelamento do Tanque VIE de O2**
12. **Plano de Emergência Hídrica Hospitalar (*CDC/EPA EWSP*) & Contingência Renal Anti-Hipercalemia**
13. **Protocolo *AABB Tiered Blood Conservation* & Ácido Tranexâmico Precoce (*CRASH-2 / WOMAN*)**
14. **Contingência de Esterilização da CME (*AAMI ST79 / RDC ANVISA 15* — Kits *Deep-Stock* & CME Cruzada)**
15. **Protocolo *PRISM* de Descontaminação Química Agroindustrial (Regra dos 15 min & Reserva de Atropina)**
16. **Matriz *TRAIN* (*Stanford*) de Evacuação Horizontal Crítica & Coorte Materno-Neonatal (*UCINCo*)**

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
