import sqlite3
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

if getattr(sys, "frozen", False):
    _APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "HRO-Gemeo-Digital"
    _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = _APP_DATA_DIR / "hro_digital_twin.db"
else:
    DB_PATH = Path(__file__).parent / "hro_digital_twin.db"

PERFISS_CLINICOS = {
    "UTI-AD": [
        ("A41.9", "Choque Séptico de Foco Pulmonar + IRA KDIGO 3", "Critico", "VM Invasiva (TOT)", 1),
        ("I21.0", "IAM com Supra de ST Pós-Angioplastia Primária", "Critico", "Cateter Nasal O2 3L/min", 1),
        ("S06.5", "TCE Grave Pós-Acidente Automotivo (BR-282) + DVE", "Critico", "VM Invasiva (TOT)", 1),
        ("I61.9", "AVC Hemorrágico intraparenquimatoso pós-drenagem", "Critico", "VM Invasiva (TOT)", 1),
        ("J96.0", "Insuficiência Respiratória Aguda Hipoxêmica (SDRA)", "Critico", "VM Invasiva (TOT)", 1),
        ("K85.9", "Pancreatite Aguda Necrosante Grave", "Grave", "VNI (BiPAP)", 0),
    ],
    "UTI-PED": [
        ("J21.0", "Bronquiolite Viral Aguda Grave (VSR+)", "Critico", "CNAFO / VNI", 0),
        ("G00.9", "Meningite Bacteriana Aguda em Monitorização Neuro", "Critico", "VM Invasiva (TOT)", 1),
        ("T07", "Politraumatismo Pediátrico", "Grave", "VM Invasiva (TOT)", 1),
    ],
    "UTI-NEO": [
        ("P07.3", "Prematuridade Extrema (29 sem) + SDR Neonatal", "Critico", "CPAP Nasal / VM Neo", 0),
        ("P36.9", "Sepse Neonatal Precoce em Antibioticoterapia", "Grave", "O2 Incubadora", 0),
        ("P22.0", "Síndrome do Desconforto Respiratório do RN", "Grave", "CPAP Nasal", 0),
    ],
    "PS-EMERG": [
        ("S72.0", "Fratura de Fêmur Proximal aguardando Centro Cirúrgico", "Grave", "Ar Ambiente", 0),
        ("I63.9", "AVC Isquêmico Agudo em Janela de Trombólise", "Critico", "Cateter O2 2L/min", 0),
        ("R57.1", "Politrauma Abdominal Fechado (Sala Vermelha)", "Critico", "VM Invasiva (TOT)", 1),
        ("J18.9", "Pneumonia Comunitária Grave em Boarding p/ Enfermaria", "Grave", "Máscara Hudson 6L/min", 0),
        ("N39.0", "Pielonefrite Aguda Obstrutiva (Aguardando Leito)", "Estavel", "Ar Ambiente", 0),
        ("K35.8", "Apendicite Aguda Supurada Pré-Operatório", "Estavel", "Ar Ambiente", 0),
        ("I50.0", "Insuficiência Cardíaca Descompensada Perfil B", "Grave", "VNI Intermitente", 0),
    ],
    "CLIN-CIR": [
        ("K80.0", "Pós-Operatório Colecistectomia Videolaparoscópica", "Pre-Alta", "Ar Ambiente", 0),
        ("S82.2", "Pós-Operatório Osteossíntese de Tíbia e Fíbula", "Estavel", "Ar Ambiente", 0),
        ("C18.9", "Pós-Operatório Colectomia Direita Videolaparoscópica", "Estavel", "Ar Ambiente", 0),
        ("I71.4", "Pós-Operatório Correção Endovascular Aneurisma Aorta", "Grave", "Cateter O2 2L/min", 0),
    ],
    "CLIN-MED": [
        ("I50.9", "Insuficiência Cardíaca Congestiva Compensando", "Estavel", "Ar Ambiente", 0),
        ("J44.1", "DPOC Exacerbado em Desmame de Corticoide", "Pre-Alta", "Cateter O2 1L/min", 0),
        ("E11.1", "Cetoacidose Diabética Resolvida em Transição Insulina SC", "Pre-Alta", "Ar Ambiente", 0),
        ("I64", "AVC Isquêmico Subagudo em Reabilitação Motora/Fono", "Estavel", "Ar Ambiente", 0),
    ],
    "ONCO-UNA": [
        ("C34.9", "Neoplasia de Pulmão em Controle de Dor e Dispneia", "Grave", "Cateter O2 3L/min", 0),
        ("C50.9", "Pós-Operatório Mastectomia Radical + Linfadenectomia", "Pre-Alta", "Ar Ambiente", 0),
        ("D70", "Neutropenia Febril Pós-Quimioterapia em Isolamento Protetor", "Grave", "Ar Ambiente", 0),
    ],
    "MAT-OBST": [
        ("O14.1", "Pré-Eclâmpsia Grave em Sulfatação (Gestação Alto Risco)", "Grave", "Ar Ambiente", 0),
        ("O82.0", "Puerpério Imediato Pós-Cesariana (Alojamento Conjunto)", "Pre-Alta", "Ar Ambiente", 0),
        ("O24.4", "Diabetes Mellitus Gestacional em Controle Glicêmico", "Estavel", "Ar Ambiente", 0),
    ],
    "PED-CLIN": [
        ("J15.9", "Pneumonia Bacteriana Pediátrica em ATB Venoso", "Estavel", "Ar Ambiente", 0),
        ("A09", "Gastroenterite Aguda com Desidratação Moderada Corrigida", "Pre-Alta", "Ar Ambiente", 0),
        ("J45.9", "Crise Asmática Moderada em Broncodilatador", "Estavel", "Cateter O2 1L/min", 0),
    ],
    "CC-SRPA": [
        ("C71.9", "PO Imediato Craniotomia p/ Ressecção Tumoral (Leito-Dependente UTI)", "Critico", "VM Invasiva (TOT)", 1),
        ("I71.0", "PO Imediato Correção de Dissecção de Aorta Torácica (Leito-Dependente UTI)", "Critico", "VM Invasiva (TOT)", 1),
        ("S36.0", "PO Imediato Laparotomia Exploradora + Esplenectomia (Leito-Dependente UTI)", "Critico", "VM Invasiva (TOT)", 1),
        ("S72.0", "PO Imediato Artroplastia Total de Quadril em Recuperação Anestésica", "Grave", "Cateter O2 3L/min", 0),
        ("K80.0", "PO Imediato Colecistectomia Videolaparoscópica em Despertar Anestésico", "Estavel", "Ar Ambiente", 0),
        ("C18.9", "PO Imediato Hemicolectomia Oncológica aguardando vaga UTI/Enfermaria", "Grave", "Máscara Hudson 5L/min", 0),
    ]
}

ALERGIAS_OPCOES = [
    "Nega alergias medicamentosas conhecidas",
    "Nega alergias medicamentosas conhecidas",
    "Nega alergias medicamentosas conhecidas",
    "ALERGIA: Dipirona Sódica (Broncoespasmo)",
    "ALERGIA: Penicilinas / Beta-lactâmicos (Rash cutâneo)",
    "ALERGIA: AINEs (Cetoprofeno / Tenoxicam)",
    "ALERGIA: Contraste Iodado"
]

ISOLAMENTOS_OPCOES = [
    "Nenhum", "Nenhum", "Nenhum", "Nenhum",
    "Contato (KPC / Multirresistente)",
    "Gotículas (Vírus Respiratório)",
    "Aerossóis (Pressão Negativa)"
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force_reset: bool = False):
    if force_reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS sectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        nome TEXT NOT NULL,
        tipo TEXT NOT NULL,
        categoria_leito TEXT NOT NULL DEFAULT 'FIXO',
        leitos_instalados INTEGER NOT NULL,
        leitos_contingencia INTEGER NOT NULL,
        leitos_bloqueados INTEGER NOT NULL DEFAULT 0,
        ocupados_atual INTEGER NOT NULL,
        medicos_turno INTEGER NOT NULL,
        enfermeiros_turno INTEGER NOT NULL,
        tecnicos_turno INTEGER NOT NULL,
        ratio_pac_por_medico REAL NOT NULL,
        ratio_pac_por_enfermeiro REAL NOT NULL,
        ratio_pac_por_tecnico REAL NOT NULL,
        ventiladores_total INTEGER NOT NULL,
        ventiladores_em_uso INTEGER NOT NULL,
        ventiladores_inoperantes INTEGER NOT NULL DEFAULT 0,
        monitores_total INTEGER NOT NULL DEFAULT 20,
        monitores_em_uso INTEGER NOT NULL DEFAULT 15,
        monitores_inoperantes INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_anonimo TEXT UNIQUE NOT NULL,
        iniciais_hash TEXT NOT NULL,
        sector_id INTEGER NOT NULL,
        leito TEXT NOT NULL,
        idade INTEGER NOT NULL,
        sexo TEXT NOT NULL,
        cid10 TEXT NOT NULL,
        diagnostico TEXT NOT NULL,
        gravidade TEXT NOT NULL,
        escore_news2 INTEGER NOT NULL,
        suporte_ventilatorio TEXT NOT NULL,
        drogas_vasoativas INTEGER NOT NULL DEFAULT 0,
        isolamento TEXT NOT NULL DEFAULT 'Nenhum',
        alergias TEXT NOT NULL DEFAULT 'Nega alergias conhecidas',
        dias_internacao INTEGER NOT NULL,
        elegivel_alta_segura INTEGER NOT NULL DEFAULT 0,
        origem_admissao TEXT NOT NULL DEFAULT 'Fluxo Regular',
        FOREIGN KEY(sector_id) REFERENCES sectors(id)
    );

    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        codigo_prescricao TEXT NOT NULL,
        data_hora TEXT NOT NULL,
        validade_ate TEXT NOT NULL,
        medico_crm TEXT NOT NULL,
        dieta TEXT NOT NULL,
        hidratacao TEXT NOT NULL,
        oxigenoterapia TEXT NOT NULL,
        cuidados_enfermagem TEXT NOT NULL,
        observacoes_clinicas TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Vigente',
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );

    CREATE TABLE IF NOT EXISTS prescription_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prescription_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        medicamento TEXT NOT NULL,
        dose TEXT NOT NULL,
        via TEXT NOT NULL,
        intervalo TEXT NOT NULL,
        aprazamento TEXT NOT NULL,
        alta_vigilancia INTEGER NOT NULL DEFAULT 0,
        status_checagem TEXT NOT NULL DEFAULT 'Aprazado',
        atraso_minutos INTEGER NOT NULL DEFAULT 0,
        em_falta_farmacia INTEGER NOT NULL DEFAULT 0,
        substituto_sugerido TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(prescription_id) REFERENCES prescriptions(id)
    );

    CREATE TABLE IF NOT EXISTS clinical_evolutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        data_hora TEXT NOT NULL,
        profissional TEXT NOT NULL,
        subjetivo TEXT NOT NULL,
        objetivo TEXT NOT NULL,
        avaliacao TEXT NOT NULL,
        plano TEXT NOT NULL,
        pa TEXT NOT NULL,
        fc INTEGER NOT NULL,
        fr INTEGER NOT NULL,
        spo2 INTEGER NOT NULL,
        tax REAL NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );

    CREATE TABLE IF NOT EXISTS pharmacy_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        termo_chave TEXT UNIQUE NOT NULL,
        nome_comercial TEXT NOT NULL,
        classe_terapeutica TEXT NOT NULL,
        criticidade TEXT NOT NULL,
        status_estoque TEXT NOT NULL DEFAULT 'NORMAL',
        autonomia_horas INTEGER NOT NULL DEFAULT 120,
        alternativa_terapeutica TEXT NOT NULL,
        dose_alternativa TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS power_grid_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        rede_externa TEXT NOT NULL DEFAULT 'NORMAL',
        status_geradores TEXT NOT NULL DEFAULT 'STANDBY_OK',
        tempo_sem_energia_min INTEGER NOT NULL DEFAULT 0,
        autonomia_bateria_vm_min INTEGER NOT NULL DEFAULT 90,
        autonomia_bateria_bic_min INTEGER NOT NULL DEFAULT 120,
        usina_oxigenio_status TEXT NOT NULL DEFAULT 'OPERACIONAL',
        observacao_contingencia TEXT NOT NULL DEFAULT 'Rede elétrica Celesc estável e 3 grupos geradores diesel em prontidão automática.'
    );

    CREATE TABLE IF NOT EXISTS it_system_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        status_sistema TEXT NOT NULL DEFAULT 'ONLINE',
        causa_queda TEXT NOT NULL DEFAULT 'Nenhuma',
        modulos_afetados TEXT NOT NULL DEFAULT 'Nenhum (PEP, Farmácia, LIS e PACS Operacionais)',
        horas_sem_sistema INTEGER NOT NULL DEFAULT 0,
        modo_operacao TEXT NOT NULL DEFAULT 'DIGITAL_ONLINE',
        prescricoes_papel_pendentes INTEGER NOT NULL DEFAULT 0,
        risco_erro_transcricao TEXT NOT NULL DEFAULT 'BAIXO',
        observacao_ti TEXT NOT NULL DEFAULT 'Sistema de Gestão Hospitalar, Prescrição Eletrônica (PEP), Farmácia e PACS/LIS 100% online.'
    );

    CREATE TABLE IF NOT EXISTS surgical_center_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        status_fluxo TEXT NOT NULL DEFAULT 'NORMAL',
        salas_cirurgicas_total INTEGER NOT NULL DEFAULT 10,
        salas_bloqueadas_pos_op INTEGER NOT NULL DEFAULT 0,
        leitos_srpa_fixos INTEGER NOT NULL DEFAULT 18,
        ocupados_srpa INTEGER NOT NULL DEFAULT 12,
        cirurgias_leito_dependentes_retidas INTEGER NOT NULL DEFAULT 1,
        pacientes_uti_alta_bloqueada INTEGER NOT NULL DEFAULT 2,
        cirurgias_eletivas_suspensas INTEGER NOT NULL DEFAULT 0,
        observacao_cc TEXT NOT NULL DEFAULT 'Centro Cirúrgico e SRPA (18 leitos) com giro regular. Vagas de UTI e Enfermaria alinhadas com mapa cirúrgico.'
    );

    CREATE TABLE IF NOT EXISTS critical_utilities_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        o2_rede_status TEXT NOT NULL DEFAULT 'NORMAL',
        o2_pressao_kgf REAL NOT NULL DEFAULT 4.8,
        o2_autonomia_horas INTEGER NOT NULL DEFAULT 96,
        agua_hemodialise_status TEXT NOT NULL DEFAULT 'NORMAL',
        pacientes_dialise_retidos INTEGER NOT NULL DEFAULT 0,
        agua_autonomia_horas INTEGER NOT NULL DEFAULT 96,
        hemoterapia_status TEXT NOT NULL DEFAULT 'NORMAL',
        bolsas_o_neg_disponiveis INTEGER NOT NULL DEFAULT 28,
        cme_autoclaves_status TEXT NOT NULL DEFAULT 'NORMAL',
        caixas_cirurgicas_estereis_pct INTEGER NOT NULL DEFAULT 100,
        hazmat_status TEXT NOT NULL DEFAULT 'NORMAL',
        vitimas_hazmat_ativas INTEGER NOT NULL DEFAULT 0,
        evacuacao_ala_status TEXT NOT NULL DEFAULT 'NORMAL',
        ala_evacuada TEXT NOT NULL DEFAULT 'Nenhuma',
        sobrecarga_materno_neonatal_status TEXT NOT NULL DEFAULT 'NORMAL',
        rn_ventilacao_bloco_obstetrico INTEGER NOT NULL DEFAULT 0,
        observacao_utilidades TEXT NOT NULL DEFAULT 'Gases medicinais (Tanque VIE 4,8 kgf/cm²), Osmose Reversa/Hemodiálise, Agência Transfusional, CME e rotas de segurança 100% operacionais (Autonomia >= 96h).'
    );

    CREATE TABLE IF NOT EXISTS contingency_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        titulo TEXT NOT NULL,
        severidade TEXT NOT NULL,
        descricao TEXT NOT NULL,
        impacto_json TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        ativo INTEGER NOT NULL DEFAULT 1
    );
    """)

    # Garantir colunas novas caso banco antigo exista
    cur.execute("PRAGMA table_info(sectors)")
    sec_cols = [c["name"] for c in cur.fetchall()]
    if "categoria_leito" not in sec_cols:
        # Se o esquema antigo existir sem categoria_leito, recriar limpo para respeitar a regra de 340 fixos + PS + 18 SRPA
        conn.close()
        if DB_PATH.exists():
            DB_PATH.unlink()
        return init_db(force_reset=False)

    cur.execute("SELECT COUNT(*) as cnt FROM sectors")
    if cur.fetchone()["cnt"] == 0:
        seed_hospital_data(conn)

    cur.execute("SELECT COUNT(*) as cnt FROM pharmacy_inventory")
    if cur.fetchone()["cnt"] == 0:
        seed_pharmacy_and_power(conn)

    cur.execute("SELECT COUNT(*) as cnt FROM it_system_state")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
            INSERT OR REPLACE INTO it_system_state (
                id, status_sistema, causa_queda, modulos_afetados, horas_sem_sistema,
                modo_operacao, prescricoes_papel_pendentes, risco_erro_transcricao, observacao_ti
            ) VALUES (
                1, 'ONLINE', 'Nenhuma', 'Nenhum (PEP, Farmácia, LIS e PACS Operacionais)', 0,
                'DIGITAL_ONLINE', 0, 'BAIXO',
                'Sistema de Gestão Hospitalar, Prescrição Eletrônica (PEP), Farmácia e PACS/LIS 100% online.'
            )
        """)

    cur.execute("SELECT COUNT(*) as cnt FROM surgical_center_state")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
            INSERT OR REPLACE INTO surgical_center_state (
                id, status_fluxo, salas_cirurgicas_total, salas_bloqueadas_pos_op,
                leitos_srpa_fixos, ocupados_srpa, cirurgias_leito_dependentes_retidas,
                pacientes_uti_alta_bloqueada, cirurgias_eletivas_suspensas, observacao_cc
            ) VALUES (
                1, 'NORMAL', 10, 0, 18, 12, 1, 2, 0,
                'Centro Cirúrgico e SRPA (18 leitos) com giro regular. Vagas de UTI e Enfermaria alinhadas com mapa cirúrgico.'
            )
        """)

    cur.execute("SELECT COUNT(*) as cnt FROM critical_utilities_state")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
            INSERT OR REPLACE INTO critical_utilities_state (
                id, o2_rede_status, o2_pressao_kgf, o2_autonomia_horas,
                agua_hemodialise_status, pacientes_dialise_retidos, agua_autonomia_horas,
                hemoterapia_status, bolsas_o_neg_disponiveis,
                cme_autoclaves_status, caixas_cirurgicas_estereis_pct,
                hazmat_status, vitimas_hazmat_ativas,
                evacuacao_ala_status, ala_evacuada,
                sobrecarga_materno_neonatal_status, rn_ventilacao_bloco_obstetrico,
                observacao_utilidades
            ) VALUES (
                1, 'NORMAL', 4.8, 96,
                'NORMAL', 0, 96,
                'NORMAL', 28,
                'NORMAL', 100,
                'NORMAL', 0,
                'NORMAL', 'Nenhuma',
                'NORMAL', 0,
                'Gases medicinais (Tanque VIE 4,8 kgf/cm²), Osmose Reversa/Hemodiálise, Agência Transfusional, CME e rotas de segurança 100% operacionais (Autonomia >= 96h).'
            )
        """)

    conn.commit()
    conn.close()


def seed_pharmacy_and_power(conn: sqlite3.Connection):
    cur = conn.cursor()
    meds = [
        ("Noradrenalina", "Noradrenalina (Hemitartarato) 4mg/4mL", "Droga Vasoativa", "VITAL", "NORMAL", 120,
         "Vasopressina 20 UI/mL ou Adrenalina 1mg/mL em BIC", "Titular p/ PAM >= 65 mmHg"),
        ("Fentanila", "Fentanila 50mcg/mL (Ampola 10mL)", "Sedoanalgesia UTI", "VITAL", "NORMAL", 96,
         "Morfina 10mg/mL EV em BIC ou Alfentanila", "2 a 5 mg/h EV Contínuo"),
        ("Piperacilina", "Piperacilina + Tazobactam 4,5g", "Antimicrobiano Amplo Espectro", "ALTA", "NORMAL", 144,
         "Meropenem 1g EV ou Cefepima 2g + Metronidazol 500mg", "1g EV 8/8h (Infusão Estendida)"),
        ("Ceftriaxona", "Ceftriaxona Dissódica 1g EV", "Antimicrobiano Cefalosporina", "ALTA", "NORMAL", 168,
         "Cefotaxima 1g EV 8/8h ou Ampicilina + Sulbactam 3g", "1g EV 8/8h"),
        ("Enoxaparina", "Enoxaparina Sódica 40mg/0,4mL SC", "Anticoagulante / Profilaxia TEV", "ALTA", "NORMAL", 120,
         "Heparina Não Fracionada 5000 UI/0,25mL SC", "5000 UI SC de 8/8h ou 12/12h"),
        ("Dipirona", "Dipirona Sódica 500mg/mL (2mL)", "Analgesia / Antitérmico", "MODERADA", "NORMAL", 180,
         "Paracetamol 750mg VO/SNE ou Cetoprofeno 100mg EV", "750mg 6/6h SN"),
        ("Ondansetrona", "Ondansetrona 4mg/2mL EV", "Antiemético", "MODERADA", "NORMAL", 150,
         "Metoclopramida 10mg/2mL EV ou Bromoprida 10mg EV", "10mg EV 8/8h SN"),
        ("Omeprazol", "Omeprazol Sódico 40mg Frasco-Ampola", "Inibidor de Bomba de Prótons", "MODERADA", "NORMAL", 90,
         "Pantoprazol 40mg EV ou Famotidina 20mg", "40mg EV 24/24h"),
        ("Insulina Regular", "Insulina Regular Humana 100 UI/mL", "Controle Glicêmico", "VITAL", "NORMAL", 200,
         "Insulina Lispro / Asparte Ultrarrápida SC", "Conforme esquema HGT capilar"),
        ("Atropina", "Sulfato de Atropina 0,5mg/mL", "Antídoto Colinérgico / HazMat", "VITAL", "NORMAL", 140,
         "Pralidoxima + Glicopirrolato EV (Protocolo PRISM Intoxicação)", "2 a 4 mg EV a cada 10-15 min até atropinização"),
        ("Gluconato de Cálcio", "Gluconato de Cálcio 10% (Ampola 10mL)", "Cardioproteção Hipercalemia / Diálise", "VITAL", "NORMAL", 160,
         "Cloreto de Cálcio 10% EV + Solução Polarizante (Glicose 50% + Insulina)", "10 a 20 mL EV lento em 5 min"),
        ("Ácido Tranexâmico", "Ácido Tranexâmico 250mg/5mL", "Antifibrinolítico / Economia de Sangue", "ALTA", "NORMAL", 180,
         "Ácido Épsilon-Aminocaproico EV + Crioprecipitado dirigido", "1g EV em 10 min + 1g em 8h"),
    ]
    cur.executemany("""
        INSERT INTO pharmacy_inventory (
            termo_chave, nome_comercial, classe_terapeutica, criticidade,
            status_estoque, autonomia_horas, alternativa_terapeutica, dose_alternativa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, meds)

    cur.execute("""
        INSERT OR REPLACE INTO power_grid_state (
            id, rede_externa, status_geradores, tempo_sem_energia_min,
            autonomia_bateria_vm_min, autonomia_bateria_bic_min,
            usina_oxigenio_status, observacao_contingencia
        ) VALUES (
            1, 'NORMAL', 'STANDBY_OK', 0, 90, 120, 'OPERACIONAL',
            'Rede elétrica Celesc estável e 3 grupos geradores diesel em prontidão automática.'
        )
    """)

    cur.execute("""
        INSERT OR REPLACE INTO it_system_state (
            id, status_sistema, causa_queda, modulos_afetados, horas_sem_sistema,
            modo_operacao, prescricoes_papel_pendentes, risco_erro_transcricao, observacao_ti
        ) VALUES (
            1, 'ONLINE', 'Nenhuma', 'Nenhum (PEP, Farmácia, LIS e PACS Operacionais)', 0,
            'DIGITAL_ONLINE', 0, 'BAIXO',
            'Sistema de Gestão Hospitalar, Prescrição Eletrônica (PEP), Farmácia e PACS/LIS 100% online.'
        )
    """)

    cur.execute("""
        INSERT OR REPLACE INTO surgical_center_state (
            id, status_fluxo, salas_cirurgicas_total, salas_bloqueadas_pos_op,
            leitos_srpa_fixos, ocupados_srpa, cirurgias_leito_dependentes_retidas,
            pacientes_uti_alta_bloqueada, cirurgias_eletivas_suspensas, observacao_cc
        ) VALUES (
            1, 'NORMAL', 10, 0, 18, 12, 1, 2, 0,
            'Centro Cirúrgico e SRPA (18 leitos) com giro regular. Vagas de UTI e Enfermaria alinhadas com mapa cirúrgico.'
        )
    """)

    cur.execute("""
        INSERT OR REPLACE INTO critical_utilities_state (
            id, o2_rede_status, o2_pressao_kgf, o2_autonomia_horas,
            agua_hemodialise_status, pacientes_dialise_retidos, agua_autonomia_horas,
            hemoterapia_status, bolsas_o_neg_disponiveis,
            cme_autoclaves_status, caixas_cirurgicas_estereis_pct,
            hazmat_status, vitimas_hazmat_ativas,
            evacuacao_ala_status, ala_evacuada,
            sobrecarga_materno_neonatal_status, rn_ventilacao_bloco_obstetrico,
            observacao_utilidades
        ) VALUES (
            1, 'NORMAL', 4.8, 96,
            'NORMAL', 0, 96,
            'NORMAL', 28,
            'NORMAL', 100,
            'NORMAL', 0,
            'NORMAL', 'Nenhuma',
            'NORMAL', 0,
            'Gases medicinais (Tanque VIE 4,8 kgf/cm²), Osmose Reversa/Hemodiálise, Agência Transfusional, CME e rotas de segurança 100% operacionais (Autonomia >= 96h).'
        )
    """)


def seed_hospital_data(conn: sqlite3.Connection):
    cur = conn.cursor()
    random.seed(20261022)

    # REGRA ESTRUTURAL HRO:
    # - 340 Leitos Fixos (Internação + UTIs): 40 + 10 + 20 + 85 + 80 + 45 + 35 + 25 = 340 leitos fixos.
    # - Ocupação do PS (PS-EMERG) conta como Leitos de Apoio (APOIO_PS).
    # - 18 Leitos na SRPA / Centro Cirúrgico (CC-SRPA, APOIO_SRPA).
    sectors_data = [
        # (codigo, nome, tipo, categoria_leito, instalados, contingencia, bloqueados, ocupados, med, enf, tec, r_med, r_enf, r_tec, vm_tot, vm_uso, vm_inop, mon_tot, mon_uso, mon_inop)
        ("UTI-AD", "UTI Geral Adulto (Alas A/B/C/D)", "UTI", "FIXO", 40, 6, 1, 38, 4, 8, 20, 10.0, 5.0, 2.0, 40, 31, 0, 40, 38, 0),
        ("UTI-PED", "UTI Pediátrica", "UTI", "FIXO", 10, 2, 0, 9, 2, 2, 5, 10.0, 5.0, 2.0, 10, 6, 0, 10, 9, 0),
        ("UTI-NEO", "UTI Neonatal & UCINCO", "UTI", "FIXO", 20, 4, 0, 18, 2, 4, 9, 10.0, 5.0, 2.0, 18, 9, 0, 20, 18, 0),
        ("CLIN-CIR", "Clínica Cirúrgica & Ortopedia/Trauma", "Enfermaria", "FIXO", 85, 10, 2, 78, 5, 8, 19, 15.0, 10.0, 4.0, 6, 2, 0, 18, 14, 0),
        ("CLIN-MED", "Clínica Médica & Neurologia/Cardio", "Enfermaria", "FIXO", 80, 8, 1, 74, 5, 8, 18, 14.0, 9.0, 4.0, 8, 3, 0, 20, 16, 0),
        ("ONCO-UNA", "Oncologia Clínica e Cirúrgica (UNACON)", "Enfermaria", "FIXO", 45, 4, 1, 40, 3, 5, 11, 14.0, 8.0, 4.0, 4, 1, 0, 12, 9, 0),
        ("MAT-OBST", "Maternidade Alto Risco & Aloj. Conjunto", "Maternidade", "FIXO", 35, 6, 0, 31, 4, 4, 9, 10.0, 9.0, 4.0, 3, 0, 0, 10, 6, 0),
        ("PED-CLIN", "Pediatria Clínica", "Enfermaria", "FIXO", 25, 4, 0, 21, 2, 3, 6, 12.0, 8.0, 4.0, 3, 0, 0, 8, 5, 0),
        ("PS-EMERG", "Pronto-Socorro / Emergência (Leitos de Apoio)", "Emergencia", "APOIO_PS", 45, 25, 0, 52, 6, 7, 18, 8.0, 6.0, 3.0, 16, 11, 0, 28, 26, 0),
        ("CC-SRPA", "Centro Cirúrgico & SRPA (18 Leitos)", "Centro Cirurgico", "APOIO_SRPA", 18, 8, 0, 12, 4, 4, 9, 6.0, 4.5, 2.0, 10, 3, 0, 18, 12, 0),
    ]

    cur.executemany("""
        INSERT INTO sectors (
            codigo, nome, tipo, categoria_leito, leitos_instalados, leitos_contingencia, leitos_bloqueados,
            ocupados_atual, medicos_turno, enfermeiros_turno, tecnicos_turno,
            ratio_pac_por_medico, ratio_pac_por_enfermeiro, ratio_pac_por_tecnico,
            ventiladores_total, ventiladores_em_uso, ventiladores_inoperantes,
            monitores_total, monitores_em_uso, monitores_inoperantes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sectors_data)

    cur.execute("SELECT * FROM sectors")
    sectors = cur.fetchall()

    seq_paciente = 1
    agora = datetime.now()

    for sector in sectors:
        for idx in range(1, sector["ocupados_atual"] + 1):
            gerar_paciente_anonimo_no_setor(cur, sector, idx, seq_paciente, agora)
            seq_paciente += 1


def gerar_paciente_anonimo_no_setor(cur, sector, idx_leito: int, seq_paciente: int, agora: datetime, origem: str = "Fluxo Regular"):
    sec_id = sector["id"]
    sec_code = sector["codigo"]
    instalados = sector["leitos_instalados"]
    lista_perfis = PERFISS_CLINICOS.get(sec_code, PERFISS_CLINICOS["CLIN-MED"])
    cid, diag, grav, vent, dva = random.choice(lista_perfis)

    if idx_leito > instalados:
        leito_nome = f"{sec_code}-EXTRA-{idx_leito - instalados:02d}"
    else:
        leito_nome = f"{sec_code}-{idx_leito:02d}"

    if sec_code == "UTI-NEO":
        idade = 0
    elif sec_code in ("UTI-PED", "PED-CLIN"):
        idade = random.randint(1, 13)
    elif sec_code == "MAT-OBST":
        idade = random.randint(18, 41)
    else:
        idade = random.randint(22, 88)

    sexo = "F" if sec_code == "MAT-OBST" else random.choice(["M", "F"])

    if grav == "Critico":
        news2 = random.randint(7, 12)
        elegivel_alta = 0
    elif grav == "Grave":
        news2 = random.randint(5, 7)
        elegivel_alta = 0
    elif grav == "Pre-Alta":
        news2 = random.randint(0, 2)
        elegivel_alta = 1
    else:
        news2 = random.randint(1, 4)
        elegivel_alta = 1 if random.random() < 0.25 else 0

    codigo_anon = f"PAC-HRO-{seq_paciente:04d}-{random.randint(10,99)}"
    iniciais_hash = f"#{random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}-{random.randint(100,999)}"
    dias_int = random.randint(1, 18)
    alergia = random.choice(ALERGIAS_OPCOES)
    isolamento = random.choice(ISOLAMENTOS_OPCOES) if grav in ("Critico", "Grave") else "Nenhum"

    cur.execute("""
        INSERT INTO patients (
            codigo_anonimo, iniciais_hash, sector_id, leito, idade, sexo,
            cid10, diagnostico, gravidade, escore_news2, suporte_ventilatorio,
            drogas_vasoativas, isolamento, alergias, dias_internacao,
            elegivel_alta_segura, origem_admissao
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        codigo_anon, iniciais_hash, sec_id, leito_nome, idade, sexo,
        cid, diag, grav, news2, vent, dva, isolamento, alergia,
        dias_int, elegivel_alta, origem
    ))
    patient_id = cur.lastrowid
    criar_prescricao_padrao(cur, patient_id, seq_paciente, grav, vent, dva, diag, alergia, agora)
    criar_evolucao_padrao(cur, patient_id, grav, vent, diag, news2, agora)
    return patient_id


def criar_prescricao_padrao(cur, patient_id, seq, grav, vent, dva, diag, alergia, agora):
    cod_presc = f"PR-2026-{seq:05d}"
    dt_str = agora.strftime("%d/%m/%Y %H:%M")
    val_str = (agora + timedelta(hours=24)).strftime("%d/%m/%Y 12:00")
    crms = ["Dr(a). Plantonista — CRM/SC 18420", "Dr(a). Intensivista — CRM/SC 21905", "Dr(a). Hospitalista — CRM/SC 15312"]
    medico = random.choice(crms)

    if "VM Invasiva" in vent:
        dieta = "Dieta Enteral Hiperproteica via SNE em Bomba de Infusão Contínua (60 mL/h)"
    elif grav == "Critico":
        dieta = "Zero / Jejum até estabilização hemodinâmica"
    else:
        dieta = "Dieta Oral Branda Hipossódica (2000 kcal/dia) fracionada 6x/dia"

    hidratacao = "Ringer Lactato 500 mL EV a 42 mL/h em Bomba de Infusão" if grav in ("Critico", "Grave") else "SF 0,9% 500 mL EV 12/12h"
    cuidados = (
        "Cabeceira elevada a 30-45°; Monitorização multiparamétrica contínua; Balanço hídrico rigoroso 6/6h; "
        "Mudança de decúbito 2/2h; Prevenção de LPP e Broncoaspiração; Glicemia capilar 6/6h."
        if grav in ("Critico", "Grave") else
        "Sinais vitais 6/6h; Cabeceira elevada 30°; Deambulação assistida; Avaliar dor (EVA) 6/6h."
    )

    cur.execute("""
        INSERT INTO prescriptions (
            patient_id, codigo_prescricao, data_hora, validade_ate, medico_crm,
            dieta, hidratacao, oxigenoterapia, cuidados_enfermagem, observacoes_clinicas, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Vigente')
    """, (
        patient_id, cod_presc, dt_str, val_str, medico,
        dieta, hidratacao, vent, cuidados,
        f"Quadro: {diag}. Atenção: {alergia}."
    ))
    presc_id = cur.lastrowid

    itens = []
    if dva:
        itens.append(("Droga Vasoativa", "Noradrenalina (Hemitartarato) 4mg/4mL (4 ampolas + SG 5% 234mL)", "Titular p/ PAM >= 65 mmHg (12 mL/h)", "EV Contínuo (BIC)", "Contínuo", "BIC 24h", 1))
        itens.append(("Sedação / Analgesia", "Fentanila 50mcg/mL (40mL + SF 0,9% 60mL)", "4 mL/h", "EV Contínuo (BIC)", "Contínuo", "BIC 24h", 1))

    if grav in ("Critico", "Grave"):
        itens.append(("Antimicrobiano", "Piperacilina + Tazobactam 4,5g", "4,5 g diluído em 100mL SF 0,9%", "EV (Infusão Estendida 3h)", "6/6h", "06:00 - 12:00 - 18:00 - 00:00", 0))
        itens.append(("Profilaxia TEV", "Enoxaparina Sódica 40mg/0,4mL", "40 mg", "SC", "24/24h", "10:00", 1))
        itens.append(("Proteção Gástrica", "Omeprazol Sódico 40mg", "40 mg", "EV", "24/24h", "06:00", 0))
    else:
        itens.append(("Antimicrobiano", "Ceftriaxona Dissódica 1g", "2 g", "EV", "24/24h", "10:00", 0))
        itens.append(("Profilaxia TEV", "Enoxaparina Sódica 40mg/0,4mL", "40 mg", "SC", "24/24h", "10:00", 1))

    if "Dipirona" not in alergia:
        itens.append(("Analgesia / Antitérmico", "Dipirona Sódica 500mg/mL (2mL)", "1 g", "EV", "6/6h SN", "06:00 - 12:00 - 18:00 - 00:00", 0))
    else:
        itens.append(("Analgesia / Antitérmico", "Paracetamol 750mg", "750 mg", "VO/SNE", "6/6h SN", "06:00 - 12:00 - 18:00 - 00:00", 0))

    itens.append(("Antiemético", "Ondansetrona 4mg/2mL", "4 mg", "EV", "8/8h SN", "06:00 - 14:00 - 22:00", 0))
    itens.append(("Controle Glicêmico", "Insulina Regular Humana 100 UI/mL (Conforme HGT)", "Se HGT 181-220: 2 UI; 221-260: 4 UI; >260: 6 UI", "SC", "6/6h ACM", "06:00 - 12:00 - 18:00 - 00:00", 1))

    for cat, med, dose, via, interv, apraz, mav in itens:
        cur.execute("""
            INSERT INTO prescription_items (
                prescription_id, categoria, medicamento, dose, via,
                intervalo, aprazamento, alta_vigilancia, status_checagem, atraso_minutos,
                em_falta_farmacia, substituto_sugerido
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Aprazado', 0, 0, '')
        """, (presc_id, cat, med, dose, via, interv, apraz, mav))


def criar_evolucao_padrao(cur, patient_id, grav, vent, diag, news2, agora):
    dt_str = (agora - timedelta(hours=2)).strftime("%d/%m/%Y %H:%M")
    if grav == "Critico":
        pa, fc, fr, spo2, tax = "102/64 (PAM 76)", 108, 22, 94, 37.8
        subj = "Paciente sob sedoanalgesia contínua (RASS -3), acoplado à ventilação mecânica."
        obj = f"Suporte: {vent}. Hemodinâmica mantida. Murmúrio vesicular presente bilateralmente. Diurese clara por SVD."
        aval = f"{diag} — Escore NEWS2: {news2} (Alto Risco Clínico)."
        plano = "Manter suporte intensivo, reavaliar desmame ventilatório e culturas em andamento."
    elif grav == "Pre-Alta":
        pa, fc, fr, spo2, tax = "120/78", 74, 16, 98, 36.5
        subj = "Paciente lúcido, orientado (Glasgow 15), refere melhora completa das queixas álgicas, aceitando bem a dieta."
        obj = "Corado, hidratado, afebril nas últimas 48h, exames laboratoriais em curva de normalização."
        aval = f"{diag} — Estável clinicamente (NEWS2: {news2}). Elegível para alta segura em plano de giro de leitos."
        plano = "Programar alta hospitalar com receita médica e orientações de retorno ambulatorial."
    else:
        pa, fc, fr, spo2, tax = "128/82", 86, 19, 96, 36.9
        subj = "Paciente consciente, orientado, refere evolução satisfatória."
        obj = f"Suporte: {vent}. Estável hemodinamicamente sem aminas vasoativas. Ferida operatória/acesso venoso sem sinais flogísticos."
        aval = f"{diag} — Em tratamento hospitalar ativo (NEWS2: {news2})."
        plano = "Manter prescrição vigente, fisioterapia motora/respiratória e controle laboratorial."

    cur.execute("""
        INSERT INTO clinical_evolutions (
            patient_id, data_hora, profissional, subjetivo, objetivo, avaliacao, plano,
            pa, fc, fr, spo2, tax
        ) VALUES (?, ?, 'Equipe Médica / Enfermagem HRO', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, dt_str, subj, obj, aval, plano, pa, fc, fr, spo2, tax))
