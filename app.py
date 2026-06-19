import streamlit as st
import pandas as pd
import psycopg2
import os
import re
import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Controle de Estoque - Aços Vital", layout="wide")

# --- OCULTAR ELEMENTOS INDESEJADOS ---
esconder_elementos = """
    <style>
    /* Esconde a marca d'água do Streamlit no rodapé */
    footer {visibility: hidden !important;}
    
    /* Esconde o botão de Deploy na barra superior */
    .stAppDeployButton {display: none !important;}
    
    /* Esconde apenas os links (ícone do GitHub) dentro da barra superior, mantendo os 3 pontinhos */
    [data-testid="stToolbar"] a {display: none !important;}
    </style>
    """
st.markdown(esconder_elementos, unsafe_allow_html=True)

# --- GPS DA IMAGEM ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
caminho_png = os.path.join(BASE_DIR, "logo.png")
caminho_jpg = os.path.join(BASE_DIR, "logo.jpg")

if os.path.exists(caminho_png):
    logo_path = caminho_png
elif os.path.exists(caminho_jpg):
    logo_path = caminho_jpg
else:
    logo_path = None

# ==========================================
# SISTEMA DE LOGIN E SEGURANÇA
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'perfil' not in st.session_state:
    st.session_state['perfil'] = ''
if 'usuario_nome' not in st.session_state:
    st.session_state['usuario_nome'] = ''

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1.5, 1, 1.5]) 
    with col2:
        if logo_path:
            st.image(logo_path, use_container_width=True)
        else:
            st.warning("⚠️ Imagem não encontrada. Certifique-se de que o nome é 'logo' e está na mesma pasta.")
            
        st.markdown("<h3 style='text-align: center;'>🔐 Acesso ao Sistema</h3>", unsafe_allow_html=True)
        usuario = st.text_input("Usuário").strip().lower()
        senha = st.text_input("Senha", type="password")
        btn_login = st.button("Entrar", use_container_width=True, type="primary")

        # --- DICIONÁRIO DE USUÁRIOS E SENHAS ---
        usuarios_pcp = {
            "denis.pcp": "Davi&Heitor",
            "joao.pcp": "46993062",
            "jonathan.pcp": "120910"
        }

        usuarios_vendas = {
            "vendas": "AcosVital@2026"
        }

        # Mapeamento de nomes amigáveis para o Log de Auditoria
        nomes_exibicao = {
            "denis.pcp": "Denis",
            "joao.pcp": "João V.",
            "jonathan.pcp": "Jonathan",
            "vendas": "Vendas"
        }

        if btn_login:
            if usuario in usuarios_pcp and senha == usuarios_pcp[usuario]:
                st.session_state['logged_in'] = True
                st.session_state['perfil'] = "PCP"
                st.session_state['usuario_nome'] = nomes_exibicao.get(usuario, usuario)
                st.rerun()
            elif usuario in usuarios_vendas and senha == usuarios_vendas[usuario]:
                st.session_state['logged_in'] = True
                st.session_state['perfil'] = "VENDEDOR"
                st.session_state['usuario_nome'] = nomes_exibicao.get(usuario, usuario)
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos!")
    
    st.stop()

# ==========================================
# BARRA LATERAL (MENU E LOGOUT)
# ==========================================
if logo_path:
    st.sidebar.image(logo_path, use_container_width=True)

st.sidebar.markdown(f"**👤 Operador:** {st.session_state['usuario_nome']}")
st.sidebar.markdown(f"**💼 Perfil:** {st.session_state['perfil']}")
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True):
    st.session_state['logged_in'] = False
    st.session_state['perfil'] = ''
    st.session_state['usuario_nome'] = ''
    st.rerun()

# ==========================================
# BANCO DE DADOS NA NUVEM (SUPABASE)
# ==========================================
st.title("📦 Sistema de Controle de Estoque")
st.markdown("---")

DATABASE_URL = st.secrets["DATABASE_URL"]

@st.cache_resource
def init_connection():
    return psycopg2.connect(DATABASE_URL)

conn = init_connection()
c = conn.cursor()

# Criação da tabela base de materiais
c.execute('''
    CREATE TABLE IF NOT EXISTS materiais (
        id SERIAL PRIMARY KEY,
        codigo TEXT,
        categoria TEXT,
        tipo TEXT,
        nome TEXT,
        dimensoes TEXT,
        unidade TEXT,
        saldo REAL,
        filial TEXT,
        valor_kg TEXT
    )
''')

# Criação da tabela de histórico (Log de Auditoria)
c.execute('''
    CREATE TABLE IF NOT EXISTS historico_movimentacao (
        id SERIAL PRIMARY KEY,
        data_hora TIMESTAMP,
        usuario TEXT,
        categoria TEXT,
        tipo TEXT,
        nome TEXT,
        dimensoes TEXT,
        unidade TEXT,
        operacao TEXT,
        quantidade REAL
    )
''')
conn.commit()

# Ajuste automático de colunas estruturais
try:
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS codigo TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS filial TEXT;")
    c.execute("ALTER TABLE materiais ADD COLUMN IF NOT EXISTS valor_kg TEXT;")
    
    c.execute("UPDATE materiais SET filial = '-' WHERE filial IS NULL")
    c.execute("UPDATE materiais SET valor_kg = '-' WHERE valor_kg IS NULL")
    
    c.execute("UPDATE materiais SET unidade = 'UNID/6', dimensoes = REPLACE(dimensoes, ' | UNID/6', '') WHERE dimensoes LIKE '% | UNID/6'")
    c.execute("UPDATE materiais SET unidade = 'UNID/12', dimensoes = REPLACE(dimensoes, ' | UNID/12', '') WHERE dimensoes LIKE '% | UNID/12'")
    c.execute("UPDATE materiais SET unidade = 'UNID' WHERE unidade IS NULL OR unidade = '-' OR unidade = ''")
    
    # Robô de Migração do Padrão Antigo para o Novo Padrão de Nomenclatura (Alma, SCH, Tubo-S)
    c.execute("SELECT id, nome, dimensoes FROM materiais")
    registros_antigos = c.fetchall()
    
    for row in registros_antigos:
        db_id, n, d = row
        update_needed = False
        
        match_alma = re.search(r'(\d+ª ALMA|ALMA \d+ª)', n)
        if match_alma and not d.startswith(match_alma.group(1)):
            n = n.replace(" " + match_alma.group(1), "")
            d = f"{match_alma.group(1)} | {d}"
            update_needed = True

        match_sch = re.search(r'(SCH \d+)', n)
        if match_sch and not d.startswith(match_sch.group(1)):
            n = n.replace(" " + match_sch.group(1), "")
            d = f"{match_sch.group(1)} | {d}"
            update_needed = True

        match_s = re.search(r'(\d+-S)', n)
        if match_s and not d.startswith(match_s.group(1)):
            n = n.replace(" " + match_s.group(1), "")
            d = f"{match_s.group(1)} | {d}"
            update_needed = True
            
        if " | SCH: " in d:
            parts = d.split(" | SCH: ")
            d = f"SCH {parts[1]} | {parts[0]}"
            update_needed = True

        if update_needed:
            c.execute("UPDATE materiais SET nome = %s, dimensoes = %s WHERE id = %s", (n.strip(), d.strip(), db_id))
            
    conn.commit()
except Exception as e:
    pass

# --- FUNÇÃO AUXILIAR: FUSO HORÁRIO DE BRASÍLIA ---
def obter_agora_br():
    tz_br = datetime.timezone(datetime.timedelta(hours=-3))
    return datetime.datetime.now(tz_br)

# --- FUNÇÃO AUXILIAR: EXIBIÇÃO DO HISTÓRICO NAS ABAS ---
def exibir_historico_operacoes():
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("⏱️ Histórico de Confirmação de Ações Recentes")
    
    c.execute('''
        SELECT data_hora, usuario, categoria, nome, dimensoes, unidade, operacao, quantidade 
        FROM historico_movimentacao 
        ORDER BY data_hora DESC LIMIT 15
    ''')
    logs = c.fetchall()
    
    if not logs:
        st.info("Nenhum registo de atividade encontrado no sistema.")
    else:
        df_logs = pd.DataFrame(logs, columns=["Data_Hora_Raw", "Quem fez a movimentação", "Categoria", "Tipo", "Dimensões", "UNID", "Entrada/Saida", "Quantidade"])
        
        df_logs['Data da movimentação'] = pd.to_datetime(df_logs['Data_Hora_Raw']).dt.strftime('%d/%m/%Y')
        df_logs['Horas da movimentação'] = pd.to_datetime(df_logs['Data_Hora_Raw']).dt.strftime('%H:%M')
        
        df_final_logs = df_logs[[
            "Data da movimentação", "Horas da movimentação", "Quem fez a movimentação", 
            "Categoria", "Tipo", "Dimensões", "UNID", "Entrada/Saida", "Quantidade"
        ]]
        
        st.dataframe(df_final_logs, use_container_width=True, hide_index=True)

# --- LÓGICA DE EXIBIÇÃO POR PERFIL ---

if st.session_state['perfil'] == "PCP":
    aba_cadastro, aba_movimentacao, aba_inventario = st.tabs(["➕ Cadastrar Material", "🔄 Movimentação", "📋 Inventário"])

    with aba_cadastro:
        st.subheader("➕ Cadastrar Novo Material")

        # Inclusão de Barra Quadrada e Barra Sextavada no catálogo oficial
        categorias_catalogo = {
            "FLANGES": ["ANSI", "AWWA C-207", "PN"],
            "CONEXÕES": ["Curva", "Cruz (ASME B16.9 ou Inox MSS SP-43)", "Redução (ASME B16.9 ou Inox MSS SP-43)", "Pestana (ASME B16.9 ou Inox MSS SP-43)", "Niple de Redução (ASME B16.9 ou MSSP-95)", "Alta Pressão / Forjadas", "Colares", "Plugs / Buchas / Niples"],
            "TUBOS": ["Aço Inox", "Com Costura", "Aço Carbono", "Mecânicos Laminados", "Calandrados de Grandes Diâmetros", "Industriais"],
            "LINHA PEAD": ["Flange Solto PEAD", "Conexões de Eletrofusão", "Conexões Injetadas", "Colarinhos Usinados", "Curvas", "Tees Segmentadas", "Redução Usinada"],
            "PERFIS LAMINADOS E DOBRADOS": ["(W) I", "(W) H - HP", "I - Abas Inclinadas", "U - Abas Inclinadas", "U - Simples", "U - Enrijecido", "Cantoneira - Abas Iguais", "Cantoneira - Abas Desiguais", "Barra Redonda", "Barra Quadrada", "Barra Sextavada", "Barra Chata"],
            "CHAPAS E GRADES": ["Fina Frio", "Fina Quente", "Grossa", "Xadrez", "Zincada", "Perfurada - Furo Redondo", "Expandida", "Piso Soldadas", "Piso Entrelaçadas", "Degraus para Escadas"],
            "CONSTRUÇÃO CIVIL": ["Vergalhões CA - 25", "Vergalhões CA - 50", "Vergalhões CA - 60", "Arame Recozido", "Barra de Transferência", "Tela Soldada Nervurada", "Telha", "Treliça"]
        }

        col1, col2 = st.columns(2)
        with col1:
            categoria = st.selectbox("Categoria", list(categorias_catalogo.keys()), key="cad_cat_principal")
        with col2:
            tipo = st.selectbox("Tipo", categorias_catalogo[categoria], key="cad_tipo_principal")
            
        st.markdown("<br>", unsafe_allow_html=True)
        col_cod, col_filial, col_valor = st.columns([1.5, 1, 1])
        with col_cod:
            codigo = st.text_input("Código do Material (Opcional)", key="cad_codigo")
            if codigo:
                codigo_limpo = codigo.strip().upper()
                c.execute("SELECT nome, dimensoes FROM materiais WHERE UPPER(codigo) = %s", (codigo_limpo,))
                registro_existente = c.fetchone()
                if registro_existente:
                    st.warning(f"⚠️ Código já cadastrado em: {registro_existente[0]} ({registro_existente[1]})")
        with col_filial:
            filial_selecionada = st.selectbox("Aços Vital (Filial)", ["SP", "MG"], key="cad_filial")
        with col_valor:
            valor_kg = st.text_input("Valor / kg (R$)", help="Ex: 15,50", key="cad_valor_kg")
        st.markdown("<hr style='margin-top: 5px; margin-bottom: 20px;'>", unsafe_allow_html=True)
                    
        nome = ""
        dimensoes_para_salvar = ""
        unidade_para_salvar = "UNID" 
        campos_vazios = False 

        if categoria == "FLANGES":
            if tipo == "ANSI":
                col3, col4, col5 = st.columns(3)
                with col3:
                    classe = st.selectbox("Classe", ["150 LBS", "300 LBS", "400 LBS", "600 LBS", "900 LBS", "1500 LBS"], key="cad_classe_ansi")
                with col4:
                    modelo = st.selectbox("Modelo", ["WN (Weld-Neck)", "SW (Socket-Weld)", "CEGO", "SOB PLANO", "SO (Slip-on)", "SOLTO"], key="cad_modelo_ansi")
                with col5:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_ansi")
                        
                nome = f"{classe} {modelo}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

            elif tipo == "AWWA C-207":
                col3, col4 = st.columns(2)
                with col3:
                    opcoes_awwa = ["Classe B (86 psi)", "Classe D (175 : 150 psi)", "Classe E (275 psi)", "Classe F (300 psi)"]
                    classe = st.selectbox("Classe e Pressão", opcoes_awwa, key="cad_classe_awwa")
                with col4:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_awwa")
                    
                nome = f"{classe}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

            elif tipo == "PN":
                col3, col4, col5 = st.columns(3)
                with col3:
                    pn_valor = st.selectbox("Pressão (PN)", ["10", "16", "25", "40", "63", "100"], key="cad_pn_val")
                with col4:
                    classe_pn = st.selectbox("Classe", ["Tipo 1", "Tipo 2", "Tipo 5", "Tipo 11", "Tipo 12"], key="cad_classe_pn")
                with col5:
                    dimensao_valor = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_pn")
                    
                nome = f"PN {pn_valor} {classe_pn}"
                dimensao_limpa = dimensao_valor.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if not dimensao_valor: campos_vazios = True

        elif categoria == "CONEXÕES":
            if tipo == "Curva":
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo_curva = st.selectbox("Modelo", ["Curva 45°", "Curva 90°", "Curva 180°", "Curva outro °"], key="cad_mod_curva")
                    if modelo_curva == "Curva outro °":
                        grau_custom = st.text_input("Qual o Grau?", key="cad_grau_curva")
                        nome = f"Curva {grau_custom}°" if grau_custom else "Curva"
                    else:
                        nome = modelo_curva
                        grau_custom = "N/A"
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_curva")
                with col5:
                    schedule = st.text_input("Schedule (Opcional)", key="cad_sch_curva")
                    
                dimensao_limpa = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom or (modelo_curva == "Curva outro °" and not grau_custom): campos_vazios = True

            elif tipo == "Cruz (ASME B16.9 ou Inox MSS SP-43)":
                col3, col4, col5 = st.columns(3)
                with col3:
                    nome = st.selectbox("Modelo", ["Te", "Cruzeta", "CAP"], key="cad_mod_cruz")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_cruz")
                with col5:
                    schedule = st.text_input("Schedule (Opcional)", key="cad_sch_cruz")
                    
                dimensao_limpa = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dimensao_limpa}"' if dimensao_limpa else ""
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom: campos_vazios = True

            elif tipo in ["Redução (ASME B16.9 ou Inox MSS SP-43)", "Niple de Redução (ASME B16.9 ou MSSP-95)"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo = st.selectbox("Modelo", ["Concêntrica", "Excêntrica"], key=f"cad_mod_{tipo[:3]}")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key=f"cad_dim1_{tipo[:3]}")
                with col5:
                    dim_red = st.text_input("Diâm. Red. (Pol)", key=f"cad_dim2_{tipo[:3]}")
                    
                col6, col7 = st.columns(2)
                with col6:
                    comp = st.text_input("Comprimento (mm)", key=f"cad_comp_{tipo[:3]}")
                with col7:
                    schedule = st.text_input("Schedule (Opcional)", key=f"cad_sch_{tipo[:3]}")
                    
                nome_base = "Redução" if "Redução" in tipo and "Niple" not in tipo else "Niple de Redução"
                nome = f"{nome_base} {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dim2 = dim_red.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" x {dim2}" | Comp: {comp}mm'
                if schedule: dimensoes_para_salvar = f"SCH {schedule.upper()} | " + dimensoes_para_salvar
                if not dim_nom or not dim_red or not comp: campos_vazios = True

            elif tipo == "Pestana (ASME B16.9 ou Inox MSS SP-43)":
                col3, col4 = st.columns(2)
                with col3:
                    modelo = st.selectbox("Modelo", ["ANSI Curto", "ANSI Longo", "MSS Tipo A", "MSS Tipo B"], key="cad_mod_pest")
                    dim_garg = st.text_input("Diâm. Garganta (mm)", key="cad_dim2_pest")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_pest")    
                    comp = st.text_input("Comprimento (mm)", key="cad_comp_pest")
                    
                nome = f"Pestana {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" | Garg: {dim_garg}mm | Comp: {comp}mm'
                if not dim_nom or not dim_garg or not comp: campos_vazios = True

            elif tipo == "Alta Pressão / Forjadas":
                col3, col4, col5 = st.columns(3)
                with col3:
                    modelo = st.selectbox("Modelo", ["Cotovelo 45°", "Cotovelo 90°", "Te", "Cruzeta", "Luva", "Meia Luva", "CAP Roscado"], key="cad_mod_alta")
                with col4:
                    classe = st.selectbox("Classe", ["Nenhum", "3000#", "6000#", "9000#"], key="cad_cla_alta")
                with col5:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_alta")
                    
                dim_tubo = st.text_input("Diâm. Tubo (Pol) - Opcional", key="cad_dim2_alta")
                    
                nome = f"{modelo} {classe}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if dim_tubo: 
                    dim2 = dim_tubo.replace('"', '').strip()
                    dimensoes_para_salvar += f' x {dim2}"'
                if not dim_nom: campos_vazios = True

            elif tipo == "Colares":
                col3, col4 = st.columns(2)
                with col3:
                    modelo = st.selectbox("Modelo", ["Colar BW", "Colar BW Weldolet", "Colar TH Roscado", "Sockolet Colar SW"], key="cad_mod_colar")
                with col4:
                    classe = st.selectbox("Classe", ["3000#", "6000#", "9000#"], key="cad_cla_colar")
                    
                dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_colar")
                nome = f"{modelo} {classe}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True

            elif tipo == "Plugs / Buchas / Niples":
                col3, col4 = st.columns(2)
                with col3:
                    nome = st.selectbox("Modelo", ["Bucha de Redução", "Bucha de Redução Sextavada", "Niple Duplo", "Plug Cabeça Quadrada", "Plug Cabeça Sextavada", "Plug Cabeça Redonda"], key="cad_mod_plug")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_plug")
                    
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True

        elif categoria == "TUBOS":
            modelos_tubos = {
                "Aço Inox": ["5-S", "10-S", "40-S", "80-S", "160-S"],
                "Com Costura": ["Leve", "Média", "Pesada"],
                "Aço Carbono": ["Nenhum","SCH 10", "SCH 20", "SCH 30", "SCH 40", "SCH 60", "SCH 80", "SCH 100", "SCH 120", "SCH 140", "SCH 160"],
                "Mecânicos Laminados": ["Com Centragem Externa", "Com Centragem Interna"],
                "Industriais": ["Redondos", "Quadrados", "Retangulares"],
                "Calandrados de Grandes Diâmetros": []
            }
            
            lista_modelos = modelos_tubos[tipo]
            
            if tipo == "Industriais":
                modelo = st.selectbox("Especificação", lista_modelos, key="cad_mod_tubo")
                
                if modelo == "Quadrados":
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        bitola = st.text_input("Bitola (mm)", key="cad_bit_quad")
                    with col4:
                        espessura = st.text_input("Espessura (mm)", key="cad_esp_quad")
                    with col5:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_quad")
                    nome = f"Tubo {tipo} {modelo}"
                    dimensoes_para_salvar = f"Bitola: {bitola}mm | Esp: {espessura}mm"
                    unidade_para_salvar = tamanho
                    if not bitola or not espessura: campos_vazios = True
                    
                elif modelo == "Retangulares":
                    col3, col4, col5, col6 = st.columns(4)
                    with col3:
                        bitola_l = st.text_input("Bitola l (mm)", key="cad_bitl_ret")
                    with col4:
                        bitola_c = st.text_input("Bitola c (mm)", key="cad_bitc_ret")
                    with col5:
                        espessura = st.text_input("Espessura (mm)", key="cad_esp_ret")
                    with col6:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_ret")
                    nome = f"Tubo {tipo} {modelo}"
                    dimensoes_para_salvar = f"Bitola: {bitola_l}x{bitola_c}mm | Esp: {espessura}mm"
                    unidade_para_salvar = tamanho
                    if not bitola_l or not bitola_c or not espessura: campos_vazios = True
                    
                else: 
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                    with col4:
                        espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                    with col5:
                        tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    nome = f"Tubo {tipo} {modelo}"
                    dim1 = dim_nom.replace('"', '').strip()
                    dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                    unidade_para_salvar = tamanho
                    if not dim_nom or not espessura: campos_vazios = True

            elif lista_modelos:
                col3, col4, col5, col6 = st.columns([2, 1, 1, 1.5])
                with col3:
                    modelo = st.selectbox("Especificação", lista_modelos, key="cad_mod_tubo")
                with col4:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                with col5:
                    espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                with col6:
                    tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    
                nome = f"Tubo {tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                if modelo and modelo != "Nenhum":
                    dimensoes_para_salvar = f'{modelo} | {dim1}" | Esp: {espessura}mm'
                else:
                    dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura: campos_vazios = True
                
            else: 
                col3, col4, col5 = st.columns([1, 1, 1.5])
                with col3:
                    dim_nom = st.text_input("Diâm. Nom. (Pol)", key="cad_dim1_tubo")
                with col4:
                    espessura = st.text_input("Espessura (mm)", key="cad_dim2_tubo")
                with col5:
                    tamanho = st.selectbox("Tamanho", ["UNID/6", "UNID/12"], key="cad_tam_tubo")
                    
                nome = f"Tubo {tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura: campos_vazios = True

        elif categoria == "LINHA PEAD":
            if tipo == "Flange Solto PEAD":
                col3, col4 = st.columns(2)
                with col3:
                    opcoes_flange = ["PN 10", "PN 16", "PN 25", "AWWA C-207 TAB.2", "AWWA C-207 TAB.6", "150 LBS", "300 LBS"]
                    modelo = st.selectbox("Modelo / Classe", opcoes_flange, key="cad_mod_pead_flange")
                with col4:
                    dim_nom = st.text_input("Diâmetro Nominal (Pol)", key="cad_dim_pead_flange")
                    
                nome = f"{tipo} {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"'
                if not dim_nom: campos_vazios = True
                
            else:
                col3, col4 = st.columns(2)
                with col3:
                    dim_nom = st.text_input("Diâmetro (Pol)", key="cad_dim_pead_geral")
                with col4:
                    classe_sdr = st.text_input("SDR / PN / Espessura (Opcional)", key="cad_sdr_pead_geral")
                    
                nome = f"{tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                dimensoes_para_salvar = f'{dim1}"' if dim1 else ""
                if classe_sdr: dimensoes_para_salvar += f" | Classe: {classe_sdr.upper()}"
                if not dim_nom: campos_vazios = True

        elif categoria == "PERFIS LAMINADOS E DOBRADOS":
            tamanho_opcoes = ["UNID/6", "UNID/12"]

            if tipo == "(W) I":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    alma_sel = st.selectbox("Alma", ["1ª Alma", "2ª Alma", "Outro"], key="cad_alma_wi")
                    if alma_sel == "Outro":
                        alma_custom = st.text_input("Nº da Alma", key="cad_alma_cust_wi")
                        alma_final = f"{alma_custom}ª Alma" if alma_custom else ""
                    else:
                        alma_final = alma_sel
                with col4:
                    dim_nom = st.text_input("Dim. Nominal (Pol)", key="cad_dim_wi")
                with col5:
                    espessura = st.text_input("Espessura (mm)", key="cad_esp_wi")
                with col6:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_wi")
                    
                nome = f"Perfil {tipo}"
                dim1 = dim_nom.replace('"', '').strip()
                prefixo_alma = f"{alma_final} | " if alma_final else ""
                dimensoes_para_salvar = f'{prefixo_alma}{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura or (alma_sel == "Outro" and not alma_custom): campos_vazios = True

            elif tipo == "(W) H - HP":
                col3, col4, col5, col6, col7 = st.columns(5)
                with col3:
                    modelo = st.selectbox("Modelo", ["W", "HP"], key="cad_mod_whp")
                with col4:
                    alma_sel = st.selectbox("Alma", ["1ª Alma", "2ª Alma", "Outro"], key="cad_alma_whp")
                    if alma_sel == "Outro":
                        alma_custom = st.text_input("Nº da Alma", key="cad_alma_cust_whp")
                        alma_final = f"{alma_custom}ª Alma" if alma_custom else ""
                    else:
                        alma_final = alma_sel
                with col5:
                    dim_nom = st.text_input("Dim. Nominal (Pol)", key="cad_dim_whp")
                with col6:
                    espessura = st.text_input("Espessura (mm)", key="cad_esp_whp")
                with col7:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_whp")
                    
                nome = f"Perfil {modelo}"
                dim1 = dim_nom.replace('"', '').strip()
                prefixo_alma = f"{alma_final} | " if alma_final else ""
                dimensoes_para_salvar = f'{prefixo_alma}{dim1}" | Esp: {espessura}mm'
                unidade_para_salvar = tamanho
                if not dim_nom or not espessura or (alma_sel == "Outro" and not alma_custom): campos_vazios = True

            elif tipo in ["I - Abas Inclinadas", "U - Abas Inclinadas"]:
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    modelo_sel = st.selectbox("Modelo", ["Alma 1ª", "Alma 2ª", "Outro"], key=f"cad_mod_{tipo[:1]}")
                    if modelo_sel == "Outro":
                        modelo_custom = st.text_input("Nº da Alma", key=f"cad_mod_cust_{tipo[:1]}")
                        modelo = f"Alma {modelo_custom}ª" if modelo_custom else ""
                    else:
                        modelo = modelo_sel
                with col4:
                    bit_h = st.text_input("Bitola h (Pol)", key=f"cad_h_{tipo[:1]}")
                with col5:
                    bit_b = st.text_input("Bitola b (Pol)", key=f"cad_b_{tipo[:1]}")
                with col6:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key=f"cad_tam_{tipo[:1]}")
                    
                nome_base = "Perfil I" if "I -" in tipo else "Perfil U"
                nome = f"{nome_base} Abas Inclinadas"
                dim_h = bit_h.replace('"', '').strip()
                dim_b = bit_b.replace('"', '').strip()
                prefixo_modelo = f"{modelo} | " if modelo else ""
                dimensoes_para_salvar = f'{prefixo_modelo}h: {dim_h}" x b: {dim_b}"'
                unidade_para_salvar = tamanho
                if not bit_h or not bit_b or (modelo_sel == "Outro" and not modelo_custom): campos_vazios = True

            elif tipo == "U - Simples":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    bit_h = st.text_input("Bitola h (mm)", key="cad_h_us")
                with col4:
                    bit_b = st.text_input("Bitola b (mm)", key="cad_b_us")
                with col5:
                    esp = st.text_input("Espessura (mm)", key="cad_esp_us")
                with col6:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_us")
                    
                nome = "Perfil U Simples"
                dimensoes_para_salvar = f"h: {bit_h}mm x b: {bit_b}mm | Esp: {esp}mm"
                unidade_para_salvar = tamanho
                if not bit_h or not bit_b or not esp: campos_vazios = True

            elif tipo == "U - Enrijecido":
                col3, col4, col5, col6, col7 = st.columns(5)
                with col3:
                    bit_h = st.text_input("Bitola h (mm)", key="cad_h_ue")
                with col4:
                    bit_b = st.text_input("Bitola b (mm)", key="cad_b_ue")
                with col5:
                    aba = st.text_input("Aba (mm)", key="cad_aba_ue")
                with col6:
                    esp = st.text_input("Esp. (mm)", key="cad_esp_ue")
                with col7:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_ue")
                    
                nome = "Perfil U Enrijecido"
                dimensoes_para_salvar = f"h: {bit_h} x b: {bit_b} x Aba: {aba} | Esp: {esp}mm"
                unidade_para_salvar = tamanho
                if not bit_h or not bit_b or not aba or not esp: campos_vazios = True

            elif tipo == "Cantoneira - Abas Iguais":
                col3, col4, col5 = st.columns(3)
                with col3:
                    bitola = st.text_input("Bitola (Pol)", key="cad_bit_cai")
                with col4:
                    esp = st.text_input("Espessura (Pol)", key="cad_esp_cai")
                with col5:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_cai")
                    
                nome = "Cantoneira Abas Iguais"
                dim1 = bitola.replace('"', '').strip()
                dim2 = esp.replace('"', '').strip()
                dimensoes_para_salvar = f'Bitola: {dim1}" | Esp: {dim2}"'
                unidade_para_salvar = tamanho
                if not bitola or not esp: campos_vazios = True

            elif tipo == "Cantoneira - Abas Desiguais":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    bit_h = st.text_input("Bitola h (Pol)", key="cad_h_cad")
                with col4:
                    bit_b = st.text_input("Bitola b (Pol)", key="cad_b_cad")
                with col5:
                    esp = st.text_input("Espessura (Pol)", key="cad_esp_cad")
                with col6:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_cad")
                    
                nome = "Cantoneira Abas Desiguais"
                dim_h = bit_h.replace('"', '').strip()
                dim_b = bit_b.replace('"', '').strip()
                dim_esp = esp.replace('"', '').strip()
                dimensoes_para_salvar = f'h: {dim_h}" x b: {dim_b}" | Esp: {dim_esp}"'
                unidade_para_salvar = tamanho
                if not bit_h or not bit_b or not esp: campos_vazios = True

            # Agrupamento inteligente de Barra Redonda, Barra Quadrada e Barra Sextavada
            elif tipo in ["Barra Redonda", "Barra Quadrada", "Barra Sextavada"]:
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (Pol)", key=f"cad_bit_{tipo.replace(' ', '_').lower()}")
                with col4:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key=f"cad_tam_{tipo.replace(' ', '_').lower()}")
                    
                nome = tipo
                dim1 = bitola.replace('"', '').strip()
                dimensoes_para_salvar = f'Bitola: {dim1}"'
                unidade_para_salvar = tamanho
                if not bitola: campos_vazios = True

            elif tipo == "Barra Chata":
                col3, col4, col5 = st.columns(3)
                with col3:
                    larg = st.text_input("Largura (Pol)", key="cad_larg_bc")
                with col4:
                    esp = st.text_input("Espessura (Pol)", key="cad_esp_bc")
                with col5:
                    tamanho = st.selectbox("Tamanho", tamanho_opcoes, key="cad_tam_bc")
                    
                nome = "Barra Chata"
                dim1 = larg.replace('"', '').strip()
                dim2 = esp.replace('"', '').strip()
                dimensoes_para_salvar = f'Larg: {dim1}" | Esp: {dim2}"'
                unidade_para_salvar = tamanho
                if not larg or not esp: campos_vazios = True

        elif categoria == "CHAPAS E GRADES":
            nome = f"Chapa {tipo}" if "Piso" not in tipo and "Degraus" not in tipo else f"Grade {tipo}"
            
            if tipo in ["Fina Frio", "Fina Quente"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key=f"cad_bit_{tipo[:4]}")
                with col4:
                    comp = st.text_input("Comprimento (m)", key=f"cad_comp_{tipo[:4]}")
                with col5:
                    larg = st.text_input("Largura (m)", key=f"cad_larg_{tipo[:4]}")
                    
                dimensoes_para_salvar = f"Bitola: {bitola}mm | {comp}m x {larg}m"
                if not bitola or not comp or not larg: campos_vazios = True

            # Correção oficial do erro "iand" para "in" para destravar o servidor
            elif tipo in ["Grossa", "Xadrez", "Zincada"]:
                col3, col4, col5 = st.columns(3)
                with col3:
                    esp = st.text_input("Espessura (Pol)", key=f"cad_esp_{tipo[:4]}")
                with col4:
                    comp = st.text_input("Comprimento (m)", key=f"cad_comp_{tipo[:4]}")
                with col5:
                    larg = st.text_input("Largura (m)", key=f"cad_larg_{tipo[:4]}")
                    
                dim1 = esp.replace('"', '').strip()
                dimensoes_para_salvar = f'Esp: {dim1}" | {comp}m x {larg}m'
                if not esp or not comp or not larg: campos_vazios = True

            elif tipo == "Perfurada - Furo Redondo":
                col3, col4, col5 = st.columns(3)
                with col3:
                    esp = st.text_input("Espessura (Pol)", key="cad_esp_perf")
                with col4:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_perf")
                with col5:
                    larg = st.text_input("Largura (m)", key="cad_larg_perf")
                    
                col6, col7 = st.columns(2)
                with col6:
                    furo = st.text_input("Ø dos furos (Pol)", key="cad_furo_perf")
                with col7:
                    ec = st.text_input("E.C (mm)", key="cad_ec_perf")
                    
                dim1 = esp.replace('"', '').strip()
                dim2 = furo.replace('"', '').strip()
                dimensoes_para_salvar = f'Esp: {dim1}" | {comp}m x {larg}m | Furo: {dim2}" | E.C: {ec}mm'
                if not esp or not comp or not larg or not furo or not ec: campos_vazios = True

            elif tipo == "Expandida":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    m_ld = st.text_input("Malha LD (mm)", key="cad_ld_exp")
                with col4:
                    m_cd = st.text_input("Malha CD (mm)", key="cad_cd_exp")
                with col5:
                    esp = st.text_input("Espessura (mm)", key="cad_esp_exp")
                with col6:
                    avanco = st.text_input("Avanço (mm)", key="cad_av_exp")
                    
                dimensoes_para_salvar = f"Malha: {m_ld}x{m_cd}mm | Esp: {esp}mm | Avanço: {avanco}mm"
                if not m_ld or not m_cd or not esp or not avanco: campos_vazios = True

            elif tipo in ["Piso Soldadas", "Piso Entrelaçadas"]:
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    tipo_grade = st.text_input("Tipo (Ex: XX-X0-000)", key=f"cad_tipo_{tipo[:6]}")
                with col4:
                    malha_b = st.text_input("Malha B (mm)", key=f"cad_mb_{tipo[:6]}")
                with col5:
                    malha_a = st.text_input("Malha A (mm)", key=f"cad_ma_{tipo[:6]}")
                with col6:
                    altura = st.text_input("Altura (mm)", key=f"cad_alt_{tipo[:6]}")
                    
                st.markdown("*Dados de Engenharia (Opcional)*")
                col7, col8 = st.columns(2)
                with col7:
                    vaos_opcoes = [str(v) for v in range(300, 2001 if tipo == "Piso Soldadas" else 1301, 100)]
                    vao = st.selectbox("Vão (mm)", vaos_opcoes, key=f"cad_vao_{tipo[:6]}")
                with col8:
                    opcoes_dados = ["C.U.D", "FLEXA"] 
                    dados = st.selectbox("Dados", opcoes_dados, key=f"cad_cud_{tipo[:6]}")
                            
                nome = f"Grade {tipo} {tipo_grade}"
                dimensoes_para_salvar = f"Malha: {malha_b}x{malha_a}mm | Alt: {altura}mm | Vão: {vao}mm | Dados: {dados}"
                        
                if not tipo_grade or not malha_b or not malha_a or not altura: campos_vazios = True

            elif tipo == "Degraus para Escadas":
                col3, col4, col5, col6, col7 = st.columns(5)
                with col3:
                    tipo_degrau = st.text_input("Tipo (Ex: XX-00/0)", key="cad_tipo_deg")
                with col4:
                    comp = st.text_input("Comp. (mm)", key="cad_comp_deg")
                with col5:
                    larg = st.text_input("Larg. (mm)", key="cad_larg_deg")
                with col6:
                    alt = st.text_input("Alt. (mm)", key="cad_alt_deg")
                with col7:
                    esp = st.text_input("Esp. (mm)", key="cad_esp_deg")
                    
                nome = f"Degrau p/ Escada {tipo_degrau}"
                dimensoes_para_salvar = f"{comp}x{larg}mm | Alt: {alt}mm | Esp: {esp}mm"
                if not tipo_degrau or not comp or not larg or not alt or not esp: campos_vazios = True

        elif categoria == "CONSTRUÇÃO CIVIL":
            if tipo in ["Vergalhões CA - 25", "Vergalhões CA - 50"]:
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (Pol)", key=f"cad_bit_v_{tipo[-2:]}")
                with col4:
                    comp = st.text_input("Comprimento (m)", key=f"cad_comp_v_{tipo[-2:]}")
                    
                nome = f"{tipo}"
                dim1 = bitola.replace('"', '').strip()
                dimensoes_para_salvar = f'Bitola: {dim1}" | Comp: {comp}m'
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Vergalhões CA - 60":
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key="cad_bit_v_60")
                with col4:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_v_60")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Bitola: {bitola}mm | Comp: {comp}m"
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Arame Recozido":
                col3, col4, col5 = st.columns(3)
                with col3:
                    bmg = st.text_input("BMG / BWG N°", key="cad_bmg_ar")
                with col4:
                    diam = st.text_input("Diâmetro (mm)", key="cad_diam_ar")
                with col5:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_ar")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"BMG: {bmg} | Ø: {diam}mm | Comp: {comp}m"
                if not bmg or not diam or not comp: campos_vazios = True

            elif tipo == "Barra de Transferência":
                col3, col4 = st.columns(2)
                with col3:
                    bitola = st.text_input("Bitola (mm)", key="cad_bit_bt")
                with col4:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_bt")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Bitola: {bitola}mm | Comp: {comp}m"
                if not bitola or not comp: campos_vazios = True

            elif tipo == "Tela Soldada Nervurada":
                ref = st.text_input("REF. (Ex: Q 138)", key="cad_ref_tsn")
                nome = f"{tipo}"
                dimensoes_para_salvar = f"REF: {ref}"
                if not ref: campos_vazios = True

            elif tipo == "Telha":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    modelo = st.selectbox("Modelo", ["Trapezoidal", "Galvalume", "Zinco", "Sanduíche"], key="cad_mod_telha")
                with col4:
                    esp = st.selectbox("Espessura (mm)", ["0,43", "0,5", "0,65"], key="cad_esp_telha")
                with col5:
                    apoio = st.selectbox("Distância entre apoios (mm)", ["2000", "2500", "2750"], key="cad_apoio_telha")
                with col6:
                    comp = st.text_input("Comprimento (m)", key="cad_comp_telha")
                    
                nome = f"Telha {modelo}"
                dimensoes_para_salvar = f"Esp: {esp}mm | Apoio: {apoio}mm | Comp: {comp}m"
                if not comp: campos_vazios = True

            elif tipo == "Treliça":
                col3, col4, col5, col6 = st.columns(4)
                with col3:
                    altura = st.text_input("Altura (cm)", key="cad_alt_trel")
                with col4:
                    banzo_sup = st.text_input("Banzo Sup. (mm)", key="cad_bsup_trel")
                with col5:
                    diagonal = st.text_input("Diagonal (mm)", key="cad_diag_trel")
                with col6:
                    banzo_inf = st.text_input("Banzo Inf. (mm)", key="cad_binf_trel")
                    
                nome = f"{tipo}"
                dimensoes_para_salvar = f"Alt: {altura}cm | Banzos/Diag: {banzo_sup} x {diagonal} x {banzo_inf} mm"
                
                if not altura or not banzo_sup or not diagonal or not banzo_inf: campos_vazios = True

        st.markdown("**Estoque Inicial (Peças Físicas)**")
        quantidade = st.number_input("Quantidade", min_value=0, step=1, key="quantidade")
            
        submit_button = st.button(label='Salvar no Banco de Dados', type="primary")

        if submit_button:
            nome_limpo = nome.strip().upper()
            dimensoes_limpas = dimensoes_para_salvar.strip().upper()
            cod_final = codigo.strip().upper() if codigo else "-"
            
            valor_kg_limpo = re.sub(r'[^0-9,]', '', valor_kg) if valor_kg else "-"
            if not valor_kg_limpo: 
                valor_kg_limpo = "-"
            
            if campos_vazios:
                st.warning("⚠️ Por favor, preencha todos os campos obrigatórios da peça!")
            else:
                c.execute('''
                    SELECT id FROM materiais 
                    WHERE categoria = %s AND tipo = %s AND nome = %s AND dimensoes = %s AND filial = %s
                ''', (categoria, tipo, nome_limpo, dimensoes_limpas, filial_selecionada))
                
                if c.fetchone():
                    st.error(f"❌ Cadastro Bloqueado: O material '{nome_limpo}' com essas dimensões já existe na filial {filial_selecionada}!")
                else:
                    c.execute('''
                        INSERT INTO materiais (codigo, categoria, tipo, nome, dimensoes, unidade, saldo, filial, valor_kg)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (cod_final, categoria, tipo, nome_limpo, dimensoes_limpas, unidade_para_salvar, quantidade, filial_selecionada, valor_kg_limpo))
                    
                    c.execute('''
                        INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (obter_agora_br(), st.session_state['usuario_nome'], categoria, tipo, nome_limpo, dimensoes_limpas, unidade_para_salvar, 'CADASTRO', quantidade))
                    
                    conn.commit()
                    st.success(f"✅ Material '{nome_limpo}' cadastrado com sucesso!")
                    st.rerun()

        exibir_historico_operacoes()

    with aba_movimentacao:
        st.subheader("🔄 Movimentação de Estoque")

        c.execute("SELECT id, codigo, categoria, tipo, nome, dimensoes, saldo, unidade, filial, valor_kg FROM materiais")
        df_materiais = pd.DataFrame(c.fetchall(), columns=["id", "codigo", "categoria", "tipo", "nome", "dimensoes", "saldo", "unidade", "filial", "valor_kg"])

        if df_materiais.empty:
            st.info("💡 Cadastre pelo menos um material no formulário acima para poder realizar movimentações.")
        else:
            df_materiais['identificador'] = df_materiais.apply(
                lambda r: f"[{r['codigo']}] {r['nome']} - {r['dimensoes']} | {r['filial']} | Saldo: {int(r['saldo'])} {r['unidade']} | R$ {r['valor_kg']}/kg" if str(r['codigo']) != "-" else f"{r['nome']} - {r['dimensoes']} | {r['filial']} | Saldo: {int(r['saldo'])} {r['unidade']} | R$ {r['valor_kg']}/kg", axis=1
            )

            st.markdown("**1. Localize o Material**")
            modo_busca = st.radio(
                "Escolha como quer localizar a peça:", 
                ["🔍 Busca Rápida (Digitar Código ou Nome)", "🗂️ Procurar por Categoria (Catálogo)"], 
                horizontal=True
            )

            df_final = pd.DataFrame()
            item_selecionado = None

            if modo_busca == "🔍 Busca Rápida (Digitar Código ou Nome)":
                st.info("💡 Dica: Clique na caixa abaixo e comece a digitar o Código ou o Nome. A lista vai filtrar automaticamente!")
                item_selecionado = st.selectbox("Digite ou selecione a peça:", df_materiais['identificador'].tolist(), key="mov_item_rapido")
                df_final = df_materiais

            else:
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    categorias_existentes = df_materiais['categoria'].unique()
                    filtro_cat = st.selectbox("Categoria:", categorias_existentes, key="mov_cat")
                    
                with col_m2:
                    df_filtrado_cat = df_materiais[df_materiais['categoria'] == filtro_cat]
                    tipos_existentes = df_filtrado_cat['tipo'].unique()
                    filtro_tipo = st.selectbox("Tipo:", tipos_existentes, key="mov_tipo")

                df_filtrado_tipo = df_filtrado_cat[df_filtrado_cat['tipo'] == filtro_tipo].copy()

                if filtro_cat == "FLANGES":
                    if filtro_tipo == "ANSI" and not df_filtrado_tipo.empty:
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            classes_possiveis = ["150 LBS", "300 LBS", "400 LBS", "600 LBS", "900 LBS", "1500 LBS"]
                            classes_existentes = [c for c in classes_possiveis if df_filtrado_tipo['nome'].str.contains(c, case=False, regex=False).any()]
                            filtro_classe = st.selectbox("Classe:", classes_existentes if classes_existentes else ["Nenhuma"], key="mov_classe_ansi")
                            if filtro_classe != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_classe, case=False, regex=False)]
                                
                        with col_m4:
                            modelos_possiveis = ["WN (Weld-Neck)", "SW (Socket-Weld)", "CEGO", "SOB PLANO", "SO (Slip-on)", "SOLTO"]
                            modelos_existentes = [m for m in modelos_possiveis if df_filtrado_tipo['nome'].str.contains(m, case=False, regex=False).any()]
                            filtro_modelo = st.selectbox("Modelo:", modelos_existentes if modelos_existentes else ["Nenhum"], key="mov_modelo_ansi")
                            if filtro_modelo != "Nenhum":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_modelo, case=False, regex=False)]

                    elif filtro_tipo == "AWWA C-207" and not df_filtrado_tipo.empty:
                        classes_possiveis = ["CLASSE B  (86 PSI)", "CLASSE D (175 : 150 PSI)", "CLASSE E  (275 PSI)", "CLASSE F  (300 PSI)"]
                        classes_existentes = [c for c in classes_possiveis if df_filtrado_tipo['nome'].str.upper().str.contains(c, case=False, regex=False).any()]
                        filtro_classe = st.selectbox("Classe:", classes_existentes if classes_existentes else ["Nenhuma"], key="mov_classe_awwa")
                        if filtro_classe != "Nenhuma":
                            df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.upper().str.contains(filtro_classe, case=False, regex=False)]

                    elif filtro_tipo == "PN" and not df_filtrado_tipo.empty:
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            pn_possiveis = ["PN 10", "PN 16", "PN 25", "PN 40", "PN 63", "PN 100"]
                            pn_existentes = [p for p in pn_possiveis if df_filtrado_tipo['nome'].str.contains(p, case=False, regex=False).any()]
                            filtro_pn = st.selectbox("Pressão (PN):", pn_existentes if pn_existentes else ["Nenhuma"], key="mov_pn_val")
                            if filtro_pn != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_pn, case=False, regex=False)]
                                
                        with col_m4:
                            classes_pn_possiveis = ["Tipo 1", "Tipo 2", "Tipo 5", "Tipo 11", "Tipo 12"]
                            classes_pn_existentes = [c for c in classes_pn_possiveis if df_filtrado_tipo['nome'].str.contains(c, case=False, regex=False).any()]
                            filtro_classe_pn = st.selectbox("Classe:", classes_pn_existentes if classes_pn_existentes else ["Nenhuma"], key="mov_classe_pn")
                            if filtro_classe_pn != "Nenhuma":
                                df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'].str.contains(filtro_classe_pn, case=False, regex=False)]

                elif filtro_cat != "FLANGES" and not df_filtrado_tipo.empty:
                    nomes_existentes = df_filtrado_tipo['nome'].unique().tolist()
                    filtro_modelo_dinamico = st.selectbox("Modelo / Especificação:", ["Todos"] + nomes_existentes, key="mov_mod_dinamico")
                    if filtro_modelo_dinamico != "Todos":
                        df_filtrado_tipo = df_filtrado_tipo[df_filtrado_tipo['nome'] == filtro_modelo_dinamico]

                df_final = df_filtrado_tipo.copy()
                
                if not df_final.empty:
                    item_selecionado = st.selectbox("Peça Exata:", df_final['identificador'].tolist(), key="mov_item_filtro")

            if item_selecionado and not df_final.empty:
                st.markdown("**2. Detalhes e Operação**")
                
                col_op2, col_op3 = st.columns(2)
                with col_op2:
                    operacao = st.radio("Operação:", ["Entrada (Soma)", "Saída (Subtrai)"], key="mov_op")
                with col_op3:
                    quantidade = st.number_input("Quantidade:", min_value=1, step=1, key="mov_qtd")
                    
                linha_selecionada = df_final[df_final['identificador'] == item_selecionado]
                id_real = int(linha_selecionada['id'].values[0])
                saldo_atual = float(linha_selecionada['saldo'].values[0])
                nome_real = f"{linha_selecionada['nome'].values[0]} {linha_selecionada['dimensoes'].values[0]}"
                
                btn_movimentar = st.button("Confirmar Movimentação", use_container_width=True, type="primary")
                
                if btn_movimentar:
                    op_log = 'ENTRADA' if operacao == "Entrada (Soma)" else 'SAÍDA'
                    if operacao == "Entrada (Soma)":
                        novo_saldo = saldo_atual + quantidade
                        msg = f"🚀 Entrada de {quantidade} unidades de '{nome_real}' realizada com sucesso!"
                    else:
                        novo_saldo = saldo_atual - quantidade
                        msg = f"📉 Saída de {quantidade} unidades de '{nome_real}' realizada com sucesso!"
                    
                    if novo_saldo < 0:
                        st.error(f"❌ Erro: Saldo insuficiente. O estoque atual é de apenas {int(saldo_atual)}.")
                    else:
                        c.execute("UPDATE materiais SET saldo = %s WHERE id = %s", (novo_saldo, id_real))
                        
                        c.execute('''
                            INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantity)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (obter_agora_br(), st.session_state['usuario_nome'], linha_selecionada['categoria'].values[0], linha_selecionada['tipo'].values[0], linha_selecionada['nome'].values[0], linha_selecionada['dimensoes'].values[0], linha_selecionada['unidade'].values[0], op_log, quantidade))
                        
                        conn.commit()
                        st.success(msg)
                        st.rerun()
            elif df_final.empty:
                st.warning("⚠️ Nenhum material encontrado no estoque com esses filtros.")

        exibir_historico_operacoes()

    # --- ABA DE INVENTÁRIO (PCP) ---
    with aba_inventario:
        st.subheader("📋 Planilha de Inventário Dinâmica")
        st.info("💡 Você pode editar as colunas **Código** e **Valor / kg** clicando duas vezes nelas. Depois, clique em Salvar.")
        
        c.execute("SELECT id, codigo, filial, categoria, nome, dimensoes, unidade, saldo, valor_kg FROM materiais ORDER BY nome")
        df_estoque = pd.DataFrame(c.fetchall(), columns=["id", "Código", "Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo", "Valor / kg"])
        
        if df_estoque.empty:
            st.info("O estoque está vazio.")
        else:
            edited_df = st.data_editor(
                df_estoque,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "id": None,
                    "Código": st.column_config.TextColumn("Código", width="small"),
                    "Aços Vital": st.column_config.TextColumn("Aços Vital", width="small"),
                    "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
                    "Tipo": st.column_config.TextColumn("Tipo", width="large"),
                    "Dimensões": st.column_config.TextColumn("Dimensões", width="large"),
                    "UNID": st.column_config.TextColumn("UNID", width="small"),
                    "Saldo": st.column_config.NumberColumn("Saldo", width="small"),
                    "Valor / kg": st.column_config.TextColumn("Valor / kg", width="small")
                },
                disabled=["Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo"],
                key="editor_inventario"
            )
            
            if st.button("💾 Salvar Alterações de Código e Valor", type="primary", use_container_width=True):
                alteracoes = st.session_state["editor_inventario"]["edited_rows"]
                if alteracoes:
                    for row_idx, col_alteradas in alteracoes.items():
                        db_id = int(df_estoque.loc[row_idx, "id"])
                        
                        c.execute("SELECT categoria, tipo, nome, dimensoes, unidade FROM materiais WHERE id = %s", (db_id,))
                        mat_info = c.fetchone()
                        
                        if "Código" in col_alteradas:
                            novo_codigo = col_alteradas["Código"]
                            novo_codigo = str(novo_codigo).strip().upper() if novo_codigo else "-"
                            c.execute("UPDATE materiais SET codigo = %s WHERE id = %s", (novo_codigo, db_id))
                            
                        if "Valor / kg" in col_alteradas:
                            novo_valor = col_alteradas["Valor / kg"]
                            novo_valor = re.sub(r'[^0-9,]', '', str(novo_valor)) if novo_valor else "-"
                            c.execute("UPDATE materiais SET valor_kg = %s WHERE id = %s", (novo_valor, db_id))
                            
                        c.execute('''
                            INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (obter_agora_br(), st.session_state['usuario_nome'], mat_info[0], mat_info[1], mat_info[2], mat_info[3], mat_info[4], 'EDIÇÃO', 0))
                            
                    conn.commit()
                    st.success("✅ Alterações salvas com sucesso no banco de dados!")
                    st.rerun()
                else:
                    st.info("💡 Nenhuma alteração foi realizada para ser salva.")
            
            st.markdown("---")
            st.subheader("🗑️ Excluir Cadastro de Material")
            st.warning("⚠️ Atenção: Esta ação apagará o material e seu saldo do banco de dados definitivamente. Utilize para corrigir erros de cadastro.")
            
            df_estoque['identificador_exclusao'] = df_estoque.apply(
                lambda r: f"[{r['Código']}] {r['Tipo']} - {r['Dimensões']} | {r['Aços Vital']} | Saldo: {int(r['Saldo'])} {r['UNID']}" if r['Código'] and r['Código'] != "-" else f"{r['Tipo']} - {r['Dimensões']} | {r['Aços Vital']} | Saldo: {int(r['Saldo'])} {r['UNID']}", axis=1
            )
            
            item_excluir = st.selectbox("Selecione o material que deseja excluir:", [""] + df_estoque['identificador_exclusao'].tolist(), key="select_excluir")
            
            if item_excluir != "":
                linha_del = df_estoque[df_estoque['identificador_exclusao'] == item_excluir]
                id_del = int(linha_del['id'].values[0])
                
                c.execute("SELECT categoria, tipo, nome, dimensoes, unidade, saldo FROM materiais WHERE id = %s", (id_del,))
                mat_info = c.fetchone()
                nome_del = f"{mat_info[2]} {mat_info[3]}"
                
                if st.button(f"🚨 Confirmar Exclusão: {nome_del}", use_container_width=True):
                    c.execute('''
                        INSERT INTO historico_movimentacao (data_hora, usuario, categoria, tipo, nome, dimensoes, unidade, operacao, quantidade)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (obter_agora_br(), st.session_state['usuario_nome'], mat_info[0], mat_info[1], mat_info[2], mat_info[3], mat_info[4], 'EXCLUSÃO', mat_info[5]))
                    
                    c.execute("DELETE FROM materiais WHERE id = %s", (id_del,))
                    conn.commit()
                    st.success(f"✅ Material '{nome_del}' removido do catálogo com sucesso!")
                    st.rerun()

        exibir_historico_operacoes()

# ==========================================
# SE FOR VENDEDOR: Visualização de Leitura (Com Histórico Opcional)
# ==========================================
elif st.session_state['perfil'] == "VENDEDOR":
    st.subheader("📋 Inventário Atualizado em Tempo Real")
    c.execute("SELECT codigo, filial, categoria, nome, dimensoes, unidade, saldo, valor_kg FROM materiais ORDER BY nome")
    df_estoque = pd.DataFrame(c.fetchall(), columns=["Código", "Aços Vital", "Categoria", "Tipo", "Dimensões", "UNID", "Saldo", "Valor / kg"])
    
    if df_estoque.empty:
        st.info("O estoque está vazio no momento.")
    else:
        st.dataframe(
            df_estoque, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Código": st.column_config.TextColumn("Código", width="small"),
                "Aços Vital": st.column_config.TextColumn("Aços Vital", width="small"),
                "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
                "Tipo": st.column_config.TextColumn("Tipo", width="large"),
                "Dimensões": st.column_config.TextColumn("Dimensões", width="large"),
                "UNID": st.column_config.TextColumn("UNID", width="small"),
                "Saldo": st.column_config.NumberColumn("Saldo", width="small"),
                "Valor / kg": st.column_config.TextColumn("Valor / kg", width="small")
            }
        )
    exibir_historico_operacoes()
