import { useState, type FormEvent } from "react"
import { Lock, LogIn, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface LoginDialogProps {
  open: boolean
  onSuccess: () => void
}

export function LoginDialog({ open, onSuccess }: LoginDialogProps) {
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!password.trim()) return
    setLoading(true)
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      })
      if (!res.ok) {
        let msg = "Parol noto'g'ri"
        try {
          const err = await res.json()
          if (err.detail) msg = err.detail
        } catch {
          // ignore
        }
        toast.error(msg)
        return
      }
      setPassword("")
      toast.success("Tizimga kirildi")
      onSuccess()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Xatolik yuz berdi")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} className="sm:max-w-sm">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Lock className="size-4" />
            </div>
            <div>
              <DialogTitle>PrintHub Kirish</DialogTitle>
              <DialogDescription>
                Davom etish uchun parol yoki PIN kiriting
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label htmlFor="loginPassword">Parol / PIN</Label>
            <Input
              id="loginPassword"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
            />
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? (
              <Loader2 className="animate-spin" />
            ) : (
              <LogIn />
            )}
            <span>Kirish</span>
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
