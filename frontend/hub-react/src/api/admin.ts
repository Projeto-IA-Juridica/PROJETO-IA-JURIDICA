import { api } from './client'

export interface ImportError {
  linha: number
  dados: string
  motivo: string
}

export interface PreviewItem {
  nome: string
  telefone: string
  cpf: string
  data_nascimento: string | null
  profissao: string | null
  empresa: string | null
  status: string
  numero_processo: string
  polo_cliente: string | null
}

export interface ImportResult {
  importados: number
  atualizados: number
  processos_novos: number
  processos_atualizados: number
  ignorados: number
  erros: ImportError[]
  preview: PreviewItem[]
}

function _buildForm(file: File): FormData {
  const form = new FormData()
  form.append('file', file)
  return form
}

export async function previewCSV(file: File): Promise<ImportResult> {
  const { data } = await api.post<ImportResult>(
    '/admin/import/clientes?preview=true',
    _buildForm(file),
    { headers: { 'Content-Type': undefined } },
  )
  return data
}

export async function importarCSV(file: File): Promise<ImportResult> {
  const { data } = await api.post<ImportResult>(
    '/admin/import/clientes?preview=false',
    _buildForm(file),
    { headers: { 'Content-Type': undefined } },
  )
  return data
}
