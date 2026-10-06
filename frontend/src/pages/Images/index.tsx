import { useMutation } from "@tanstack/react-query";
import { ExternalLink, ImageUp } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Button, Card, CardTitle, Field, Input, PageHeader } from "@/components/ui";
import { api, qs, type Evidence } from "@/lib/api";
import { cn, openExternal } from "@/lib/utils";

type Provedores = Record<string, { nome: string; abrir: string; upload_manual: string; por_url: string | null }>;

function ProviderButtons({ provedores }: { provedores: Provedores }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {Object.entries(provedores).map(([id, p]) => (
        <Card key={id} className="flex flex-col gap-2">
          <strong className="text-sm">{p.nome}</strong>
          <div className="flex flex-wrap gap-2">
            {p.por_url && (
              <Button size="sm" onClick={() => openExternal(p.por_url!)}>
                <ExternalLink size={14} /> Buscar pela URL
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => openExternal(p.upload_manual)}>
              <ExternalLink size={14} /> {id === "sensity" ? "Analisar com Sensity" : "Upload manual"}
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default function ImagesPage() {
  const [file, setFile] = React.useState<File | null>(null);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [origem, setOrigem] = React.useState("");
  const [drag, setDrag] = React.useState(false);
  const [provedores, setProvedores] = React.useState<Provedores | null>(null);
  const [evidencia, setEvidencia] = React.useState<Evidence | null>(null);

  React.useEffect(() => {
    if (!file) return setPreview(null);
    const u = URL.createObjectURL(file);
    setPreview(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  const enviar = useMutation({
    mutationFn: async () => {
      if (!file) {
        return api.get<{ provedores: Provedores }>(`/api/images/deeplinks${qs({ url: origem })}`);
      }
      const fd = new FormData();
      fd.append("arquivo", file);
      if (origem) fd.append("origem_url", origem);
      return api.post<{ provedores: Provedores; evidencia: Evidence }>("/api/images/upload", fd);
    },
    onSuccess: (r) => {
      setProvedores(r.provedores);
      setEvidencia("evidencia" in r ? (r as { evidencia: Evidence }).evidencia : null);
    },
  });

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f?.type.startsWith("image/")) setFile(f);
  };

  return (
    <>
      <PageHeader title="Busca reversa de imagens" description="Upload vira evidência com SHA-256; deeplinks para Google Imagens, TinEye, Yandex, Lenso e Sensity." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Imagem</CardTitle>
          <label
            htmlFor="imgfile"
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={cn("flex min-h-[12rem] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-4 text-sm", drag ? "border-primary bg-muted" : "border-border")}
          >
            {preview ? <img src={preview} alt="Pré-visualização da imagem selecionada" className="max-h-64 rounded-md" /> : (
              <>
                <ImageUp size={32} aria-hidden />
                <span className="mt-2">Arraste uma imagem ou clique para escolher</span>
              </>
            )}
          </label>
          <input id="imgfile" type="file" accept="image/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="mt-3">
            <Field label="URL pública da imagem (opcional — habilita busca direta)" htmlFor="imgurl">
              <Input id="imgurl" type="url" value={origem} onChange={(e) => setOrigem(e.target.value)} placeholder="https://…/foto.jpg" />
            </Field>
          </div>
          <Button className="mt-3" disabled={(!file && !origem) || enviar.isPending} onClick={() => enviar.mutate()}>
            Gerar buscas reversas
          </Button>
          <ErrorText error={enviar.error} />
        </Card>
        <div className="space-y-3">
          <Alert variant="info">
            A imagem local <strong>não</strong> é enviada automaticamente a terceiros. Sem URL pública, use “Upload manual” em cada provedor.
          </Alert>
          {evidencia && <Alert variant="success">Salva como evidência #{evidencia.id} — sha256 <span className="code">{evidencia.sha256}</span></Alert>}
          {provedores && <ProviderButtons provedores={provedores} />}
        </div>
      </div>
    </>
  );
}
