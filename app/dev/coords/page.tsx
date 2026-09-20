'use client';

/**
 * 좌표 입력 도구 (개발용) — /dev/coords
 *
 * 왜 필요한가:
 *  엔진은 노드 ID 만 주고 좌표는 UI 가 소유한다(data/coords.json).
 *  노드가 60~100개라 손으로 좌표를 적으면 시간이 다 날아간다.
 *  여기서 지도를 클릭해서 찍고, [JSON 복사] 로 coords.json 전체를 받아 붙여 넣으면 된다.
 *
 * 사용 순서
 *  1. 위에서 도면을 고른다
 *  2. 오른쪽 목록에서 아직 안 찍은 노드를 클릭한다 (또는 ID 를 직접 입력)
 *  3. 도면에서 해당 위치를 클릭한다
 *  4. 점을 드래그해서 미세 조정한다
 *  5. [JSON 복사] → data/coords.json 에 붙여넣기
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { Check, Copy, MapPin, Trash2 } from 'lucide-react';
import type { CoordMap } from '@/lib/types';
import { COORDS } from '@/lib/ui/coords';
import { ALL_MAPS, getMapMeta } from '@/lib/ui/maps';
import { useNodes } from '@/lib/ui/useNodes';
import { cn } from '@/lib/ui/cn';

export default function CoordsDevPage() {
  const { nodes, status: nodesStatus } = useNodes();

  const [draft, setDraft] = useState<CoordMap>(() => ({ ...COORDS }));
  const [activeSrc, setActiveSrc] = useState<string>(ALL_MAPS[0]?.src ?? '/maps/campus.svg');
  const [nodeId, setNodeId] = useState('');
  const [copied, setCopied] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);

  const movedRef = useRef(false);
  const suppressClickRef = useRef(false);
  const mapRef = useRef<HTMLDivElement>(null);

  const meta = getMapMeta(activeSrc);

  const pointsHere = useMemo(
    () =>
      Object.entries(draft)
        .filter(([, c]) => c.svg === activeSrc)
        .map(([id, c]) => ({ id, ...c })),
    [draft, activeSrc],
  );

  const toViewBox = useCallback(
    (clientX: number, clientY: number) => {
      const rect = mapRef.current?.getBoundingClientRect();
      if (!rect || rect.width === 0 || rect.height === 0) return null;
      const x = Math.round(((clientX - rect.left) / rect.width) * meta.width);
      const y = Math.round(((clientY - rect.top) / rect.height) * meta.height);
      return {
        x: Math.max(0, Math.min(meta.width, x)),
        y: Math.max(0, Math.min(meta.height, y)),
      };
    },
    [meta.width, meta.height],
  );

  const place = (id: string, x: number, y: number) => {
    setDraft((prev) => ({ ...prev, [id]: { svg: activeSrc, x, y } }));
  };

  const remove = (id: string) => {
    setDraft((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const json = useMemo(() => {
    const sorted = Object.keys(draft)
      .sort((a, b) => a.localeCompare(b))
      .reduce<CoordMap>((acc, key) => {
        acc[key] = draft[key];
        return acc;
      }, {});
    return `${JSON.stringify(sorted, null, 2)}\n`;
  }, [draft]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const unmapped = useMemo(() => nodes.filter((n) => !draft[n.id]), [nodes, draft]);
  const mapped = useMemo(() => nodes.filter((n) => draft[n.id]), [nodes, draft]);

  return (
    <div className="min-h-dvh bg-slate-100">
      <header className="border-b border-slate-200 bg-white px-4 py-3.5 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-slate-900">좌표 입력 도구</h1>
            <p className="text-[13px] text-slate-600">
              도면을 클릭해 노드 좌표를 찍고, JSON 을 복사해 <code className="rounded bg-slate-100 px-1">data/coords.json</code> 에 붙여 넣으세요.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-[12px] font-semibold text-slate-700">
              찍은 지점 {Object.keys(draft).length}개
            </span>
            <button
              type="button"
              onClick={copy}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-900"
            >
              {copied ? <Check className="size-4" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
              {copied ? '복사됨' : 'JSON 복사'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
        {/* 도면 선택 */}
        <div className="mb-3 flex flex-wrap gap-1.5">
          {ALL_MAPS.map((m) => (
            <button
              key={m.src}
              type="button"
              onClick={() => setActiveSrc(m.src)}
              className={cn(
                'min-h-11 rounded-full border px-3.5 text-sm font-semibold transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-blue-500',
                m.src === activeSrc
                  ? 'border-slate-900 bg-slate-900 text-white'
                  : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_320px] lg:items-start">
          {/* 도면 */}
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <label htmlFor="node-id" className="text-sm font-semibold text-slate-700">
                찍을 노드 ID
              </label>
              <input
                id="node-id"
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
                list="node-id-list"
                placeholder="bukak_4f_411"
                className="min-h-11 flex-1 rounded-xl border border-slate-300 px-3 font-mono text-[13px] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              />
              <datalist id="node-id-list">
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.label}
                  </option>
                ))}
              </datalist>
            </div>

            <div
              ref={mapRef}
              onClick={(e) => {
                if (suppressClickRef.current) {
                  suppressClickRef.current = false;
                  return;
                }
                const id = nodeId.trim();
                if (!id) return;
                const p = toViewBox(e.clientX, e.clientY);
                if (!p) return;
                place(id, p.x, p.y);
                setNodeId('');
              }}
              onPointerMove={(e) => {
                if (!dragId) return;
                const p = toViewBox(e.clientX, e.clientY);
                if (!p) return;
                movedRef.current = true;
                place(dragId, p.x, p.y);
              }}
              onPointerUp={() => {
                if (!dragId) return;
                suppressClickRef.current = movedRef.current;
                setDragId(null);
                movedRef.current = false;
              }}
              onPointerLeave={() => {
                if (dragId) {
                  setDragId(null);
                  movedRef.current = false;
                }
              }}
              className={cn(
                'relative overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-sm',
                nodeId.trim() ? 'cursor-crosshair' : 'cursor-default',
              )}
              style={{ aspectRatio: `${meta.width} / ${meta.height}` }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={meta.src} alt={`${meta.label} 도면`} className="absolute inset-0 h-full w-full" draggable={false} />

              {pointsHere.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  title={`${p.id} (${p.x}, ${p.y})`}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setDragId(p.id);
                    movedRef.current = false;
                  }}
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    left: `${(p.x / meta.width) * 100}%`,
                    top: `${(p.y / meta.height) * 100}%`,
                    transform: 'translate(-50%, -50%)',
                  }}
                  className={cn(
                    'absolute grid size-5 place-items-center rounded-full border-2 border-white shadow-md transition',
                    dragId === p.id ? 'scale-125 bg-blue-600' : 'bg-rose-500 hover:scale-110',
                  )}
                  aria-label={`${p.id} 좌표 ${p.x}, ${p.y} — 드래그해서 위치 수정`}
                >
                  <span className="size-1.5 rounded-full bg-white" aria-hidden="true" />
                </button>
              ))}

              {pointsHere.map((p) => (
                <span
                  key={`${p.id}-label`}
                  style={{
                    left: `${(p.x / meta.width) * 100}%`,
                    top: `${(p.y / meta.height) * 100}%`,
                    transform: 'translate(-50%, 12px)',
                  }}
                  className="pointer-events-none absolute whitespace-nowrap rounded bg-slate-900/85 px-1.5 py-0.5 font-mono text-[10px] text-white"
                >
                  {p.id}
                </span>
              ))}

              {!nodeId.trim() && (
                <p className="pointer-events-none absolute left-3 top-3 rounded-lg bg-slate-900/80 px-2.5 py-1.5 text-[12px] font-semibold text-white">
                  먼저 노드 ID를 입력하거나 오른쪽 목록에서 고르세요
                </p>
              )}
            </div>

            <p className="mt-2 text-[12px] text-slate-500">
              viewBox {meta.width}×{meta.height} · 이 도면에 찍힌 지점 {pointsHere.length}개
            </p>

            {/* JSON 미리보기 — 클립보드가 막힌 환경에서는 여기서 직접 복사 */}
            <details className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
              <summary className="cursor-pointer text-sm font-semibold text-slate-700">
                coords.json 내용 보기 / 직접 복사
              </summary>
              <textarea
                readOnly
                value={json}
                rows={14}
                className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-mono text-[11px] leading-relaxed text-slate-800"
              />
            </details>
          </div>

          {/* 노드 목록 */}
          <aside className="flex flex-col gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">
                아직 안 찍은 노드 {nodesStatus === 'loading' ? '…' : `(${unmapped.length})`}
              </h2>
              {unmapped.length === 0 ? (
                <p className="text-[13px] text-slate-500">전부 찍었습니다.</p>
              ) : (
                <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto">
                  {unmapped.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        onClick={() => setNodeId(n.id)}
                        className={cn(
                          'flex w-full min-h-11 items-center justify-between gap-2 rounded-lg px-2.5 text-left text-[13px] transition',
                          nodeId === n.id ? 'bg-blue-50 text-blue-900' : 'hover:bg-slate-50',
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-slate-800">{n.label}</span>
                          <span className="block truncate font-mono text-[11px] text-slate-500">{n.id}</span>
                        </span>
                        <MapPin className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-3">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">
                찍은 노드 ({Object.keys(draft).length})
              </h2>
              <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto">
                {Object.entries(draft)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([id, c]) => (
                    <li key={id} className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setActiveSrc(c.svg)}
                        className="flex min-h-11 min-w-0 flex-1 flex-col justify-center rounded-lg px-2.5 text-left transition hover:bg-slate-50"
                      >
                        <span className="truncate font-mono text-[11px] text-slate-800">{id}</span>
                        <span className="truncate text-[11px] text-slate-500">
                          {getMapMeta(c.svg).short} · {c.x}, {c.y}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(id)}
                        aria-label={`${id} 좌표 삭제`}
                        className="grid size-11 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
              </ul>
              {mapped.length > 0 && (
                <p className="mt-2 text-[11px] text-slate-500">
                  검색 가능한 노드 중 {mapped.length}개가 지도에 표시됩니다.
                </p>
              )}
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
