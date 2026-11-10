import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input, Select, Textarea } from '@/components/ui/input'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface FieldDef {
  name: string
  label: string
  type?: 'text' | 'number' | 'email' | 'tel' | 'date' | 'textarea' | 'select' | 'file' | 'checkbox' | 'multiselect'
  options?: { value: string | number; label: string; group?: string }[]
  required?: boolean
  /** Une valeur vide est envoyée comme null (sinon la clé est omise et la valeur par défaut du serveur s'applique). */
  nullable?: boolean
  placeholder?: string
  step?: string
  hint?: string
  full?: boolean
  /** Types de fichiers acceptés (champ « file »), ex. « .pdf,image/* ». */
  accept?: string
}

type Values = Record<string, unknown>

interface FormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  fields: FieldDef[]
  defaultValues?: Values
  submitLabel?: string
  onSubmit: (payload: Values | FormData) => Promise<unknown>
}

function groupOptions(options: FieldDef['options'] = []): [string, NonNullable<FieldDef['options']>][] {
  const groupes = new Map<string, NonNullable<FieldDef['options']>>()
  for (const o of options) groupes.set(o.group ?? '', [...(groupes.get(o.group ?? '') ?? []), o])
  return [...groupes.entries()]
}

/** Construit le corps de requête : JSON, ou FormData dès qu'un fichier est présent. */
export function buildPayload(fields: FieldDef[], values: Values): Values | FormData {
  const out: Values = {}
  let hasFile = false
  for (const f of fields) {
    const v = values[f.name]
    if (f.type === 'multiselect') {
      // react-hook-form renvoie les cases cochées sous forme de chaînes ; l'API attend des identifiants.
      const ids = (Array.isArray(v) ? v : v ? [v] : []).map((x) => Number(x)).filter((x) => Number.isFinite(x))
      out[f.name] = ids
      continue
    }
    if (f.type === 'file') {
      const file = (v as FileList | undefined)?.[0]
      if (file) {
        out[f.name] = file
        hasFile = true
      }
      continue
    }
    if (v === '' || v === undefined || v === null) {
      if (f.nullable) out[f.name] = null
      else if (f.type === 'text' || f.type === 'textarea' || f.type === 'email' || f.type === 'tel') out[f.name] = ''
      continue
    }
    out[f.name] = v
  }
  if (!hasFile) return out
  const fd = new FormData()
  for (const [k, v] of Object.entries(out)) {
    if (Array.isArray(v)) {
      // Une liste vide ne peut pas s'écrire en formulaire : un marqueur dit au serveur de la vider.
      if (v.length === 0) fd.append(`${k}__present`, '1')
      v.forEach((item) => fd.append(k, String(item)))
    } else if (v !== null) fd.append(k, v instanceof File ? v : String(v))
  }
  return fd
}

export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  fields,
  defaultValues = {},
  submitLabel = 'Enregistrer',
  onSubmit,
}: FormDialogProps) {
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ defaultValues })
  const [formError, setFormError] = useState('')

  useEffect(() => {
    if (open) {
      reset(defaultValues)
      setFormError('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const submit = handleSubmit(async (values) => {
    setFormError('')
    try {
      await onSubmit(buildPayload(fields, values))
      onOpenChange(false)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'validation_error') {
        const known = new Set(fields.map((f) => f.name))
        const general: string[] = []
        for (const [name, message] of Object.entries(error.fieldErrors())) {
          if (known.has(name)) setError(name, { message })
          else general.push(message)
        }
        setFormError(general.join(' '))
      } else {
        setFormError(error instanceof Error ? error.message : 'Une erreur est survenue.')
      }
    }
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            {fields.map((f) => {
              const err = errors[f.name]?.message as string | undefined
              const common = {
                id: `f-${f.name}`,
                'aria-invalid': err ? true : undefined,
                'aria-describedby': err ? `e-${f.name}` : undefined,
              }
              return (
                <div key={f.name} className={cn('grid gap-1.5', (f.full || f.type === 'textarea') && 'sm:col-span-2')}>
                  <label htmlFor={common.id} className="text-sm font-medium">
                    {f.label}
                    {f.required && <span className="text-destructive"> *</span>}
                  </label>
                  {f.type === 'checkbox' ? (
                    <label className="flex h-10 items-center gap-2 text-sm">
                      <input type="checkbox" className="h-4 w-4 rounded border-input accent-primary" {...register(f.name)} />
                      {f.hint ?? 'Oui'}
                    </label>
                  ) : f.type === 'multiselect' ? (
                    <div className="max-h-52 space-y-3 overflow-y-auto rounded-md border border-input bg-card p-3" role="group" aria-label={f.label}>
                      {groupOptions(f.options).map(([groupe, opts]) => (
                        <fieldset key={groupe}>
                          {groupe && <legend className="mb-1 text-xs font-medium text-muted-foreground">{groupe}</legend>}
                          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
                            {opts.map((o) => (
                              <label key={o.value} className="flex items-center gap-2 text-sm">
                                <input type="checkbox" value={o.value} className="h-4 w-4 rounded border-input accent-primary" {...register(f.name)} />
                                {o.label}
                              </label>
                            ))}
                          </div>
                        </fieldset>
                      ))}
                      {(f.options?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Chargement…</p>}
                    </div>
                  ) : f.type === 'textarea' ? (
                    <Textarea {...common} rows={3} placeholder={f.placeholder} {...register(f.name)} />
                  ) : f.type === 'select' ? (
                    <Select {...common} {...register(f.name)}>
                      {!f.required && <option value="">—</option>}
                      {f.options?.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  ) : f.type === 'file' ? (
                    <Input {...common} type="file" accept={f.accept ?? 'image/*'} {...register(f.name)} />
                  ) : (
                    <Input
                      {...common}
                      type={f.type ?? 'text'}
                      step={f.type === 'number' ? (f.step ?? 'any') : undefined}
                      placeholder={f.placeholder}
                      {...register(f.name, { required: f.required ? 'Ce champ est requis.' : false })}
                    />
                  )}
                  {f.hint && !err && <p className="text-xs text-muted-foreground">{f.hint}</p>}
                  {err && (
                    <p id={`e-${f.name}`} role="alert" className="text-xs text-destructive">
                      {err}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
          {formError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {formError}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
