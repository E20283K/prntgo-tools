import { useCallback, useEffect, useState } from "react"
import { Cog, Loader2, PlusCircle, Save, Search } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { apiFetch, type GearItem, type GearsResponse } from "@/lib/api"

interface GearsTabProps {
  active: boolean
}

export function GearsTab({ active }: GearsTabProps) {
  const [gears, setGears] = useState<GearItem[]>([])
  const [search, setSearch] = useState("")

  const [gearNum, setGearNum] = useState("")
  const [printLen, setPrintLen] = useState("")
  const [filmLen, setFilmLen] = useState("")
  const [pitch, setPitch] = useState("")
  const [saving, setSaving] = useState(false)

  const loadGears = useCallback(async () => {
    try {
      const res = await apiFetch("/api/label-imp/gears")
      const data: GearsResponse = await res.json()
      setGears(data.gears)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Vallar yuklanmadi")
    }
  }, [])

  useEffect(() => {
    if (active) {
      void loadGears()
    }
  }, [active, loadGears])

  async function handleSave() {
    const gear = parseInt(gearNum, 10)
    const pLen = parseFloat(printLen)
    const fLen = parseFloat(filmLen)
    const pitchVal = parseFloat(pitch) || +(pLen / Math.PI).toFixed(2)

    if (!gear || !pLen || !fLen) {
      toast.error("Val raqami, Printing va Film uzunligini kiriting.")
      return
    }

    setSaving(true)
    try {
      await apiFetch("/api/label-imp/gears", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gear,
          pitch_diameter: pitchVal,
          plate_thickness: 1.7,
          cylinder_diameter: +(pitchVal - 3.4).toFixed(2),
          film_length: fLen,
          printing_length: pLen,
          available: true,
        }),
      })
      toast.success(`${gear}-val saqlandi`)
      setGearNum("")
      setPrintLen("")
      setFilmLen("")
      setPitch("")
      await loadGears()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Saqlashda xatolik")
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(g: GearItem, nextVal: boolean) {
    setGears((prev) =>
      prev.map((item) =>
        item.gear === g.gear ? { ...item, available: nextVal } : item
      )
    )
    try {
      await apiFetch(`/api/label-imp/gears/${g.gear}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ available: nextVal }),
      })
      toast.success(`${g.gear}-val holati yangilandi`)
    } catch (err) {
      setGears((prev) =>
        prev.map((item) =>
          item.gear === g.gear ? { ...item, available: !nextVal } : item
        )
      )
      toast.error(err instanceof Error ? err.message : "Holat yangilanmadi")
    }
  }

  const q = search.trim().toLowerCase()
  const filtered = gears.filter((g) => !q || String(g.gear).includes(q))

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Cog className="size-5 text-muted-foreground" />
          Vallar (Gears) Boshqaruvi
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Mavjud bosma vallarni boshqaring. O'zgarishlar Web va Telegram Bot uchun darhol kuchga kiradi.
        </p>
      </div>

      {/* Add / Edit Gear */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PlusCircle className="size-4 text-muted-foreground" />
            Yangi val qo'shish / tahrirlash
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="gearNum">Val № (Gear)</Label>
              <Input
                id="gearNum"
                type="number"
                placeholder="59"
                className="tabular-nums"
                value={gearNum}
                onChange={(e) => setGearNum(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="gearPrintLen">Printing Length (mm)</Label>
              <Input
                id="gearPrintLen"
                type="number"
                step="0.01"
                placeholder="187.33"
                className="tabular-nums"
                value={printLen}
                onChange={(e) => setPrintLen(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="gearFilmLen">Film Length (mm)</Label>
              <Input
                id="gearFilmLen"
                type="number"
                step="0.01"
                placeholder="177.26"
                className="tabular-nums"
                value={filmLen}
                onChange={(e) => setFilmLen(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="gearPitch">Pitch Diameter (mm)</Label>
              <Input
                id="gearPitch"
                type="number"
                step="0.01"
                placeholder="59.63"
                className="tabular-nums"
                value={pitch}
                onChange={(e) => setPitch(e.target.value)}
              />
            </div>
          </div>
          <Button size="sm" onClick={() => void handleSave()} disabled={saving}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />}
            <span>Saqlash</span>
          </Button>
        </CardContent>
      </Card>

      {/* All Gears Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Barcha vallar
            <Badge variant="secondary" className="tabular-nums">
              {filtered.length}
            </Badge>
          </CardTitle>
          <CardAction>
            <div className="relative w-56">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Val raqami bo'yicha qidirish..."
                className="pl-8"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </CardAction>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Val №</TableHead>
                  <TableHead>Printing (mm)</TableHead>
                  <TableHead>Film (mm)</TableHead>
                  <TableHead>Pitch Ø</TableHead>
                  <TableHead>Holati</TableHead>
                  <TableHead className="text-right">Mavjud</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((g) => (
                  <TableRow key={g.gear}>
                    <TableCell className="font-semibold tabular-nums">
                      {g.gear}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {g.printing_length} mm
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {g.film_length} mm
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {g.pitch_diameter} mm
                    </TableCell>
                    <TableCell>
                      <Badge variant={g.available ? "secondary" : "outline"}>
                        {g.available ? "Mavjud" : "O'chirilgan"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Switch
                        checked={g.available}
                        onCheckedChange={(checked) =>
                          void handleToggle(g, checked)
                        }
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
