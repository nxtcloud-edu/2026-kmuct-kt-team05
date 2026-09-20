'use client';

/**
 * 출발/도착 선택 + 자연어 입력.
 *
 * 중요한 설계 원칙:
 *  LLM(자연어 파싱)이 죽어도 드롭다운으로 경로를 낼 수 있어야 한다.
 *  parseNaturalLanguage() 가 null 을 반환하면 조용히 안내만 띄우고 흐름을 유지한다.
 *  (데모 중 API 터지는 게 해커톤 1위 사망 원인)
 */

import { useCallback, useState } from 'react';
import { ArrowUpDown, Loader2, Send, Sparkles } from 'lucide-react';
import { parseNaturalLanguage } from '@/lib/client';
import type { NodeSummary, ParseResult, TravelMode, Weather } from '@/lib/types';
import { TRAVEL_MODE_LABEL } from '@/lib/types';
import { NodeCombobox } from './NodeCombobox';
import { cn } from '@/lib/ui/cn';

/** 이 값 미만이면 사용자에게 확인을 받는다 */
const CONFIDENCE_THRESHOLD = 0.6;

interface SearchPanelProps {
  nodes: NodeSummary[];
  nodesLoading: boolean;
  fromNodeId: string | null;
  toNodeId: string | null;
  onFromChange: (nodeId: string | null) => void;
  onToChange: (nodeId: string | null) => void;
  onSwap: () => void;
  onModeSuggest: (mode: TravelMode) => void;
  onWeatherSuggest: (weather: Weather) => void;
}

type ParseState =
  | { kind: 'idle' }
  | { kind: 'pending' }
  | { kind: 'unavailable' }
  | { kind: 'done'; result: ParseResult; needsConfirm: boolean };

export function SearchPanel({
  nodes,
  nodesLoading,
  fromNodeId,
  toNodeId,
  onFromChange,
  onToChange,
  onSwap,
  onModeSuggest,
  onWeatherSuggest,
}: SearchPanelProps) {
  const [text, setText] = useState('');
  const [parse, setParse] = useState<ParseState>({ kind: 'idle' });

  const submit = useCallback(
    async (raw: string) => {
      const query = raw.trim();
      if (!query) return;

      setParse({ kind: 'pending' });
      const result = await parseNaturalLanguage(query, fromNodeId ?? undefined);

      if (!result) {
        // LLM 사용 불가 — 드롭다운 흐름은 그대로 살아있다.
        setParse({ kind: 'unavailable' });
        return;
      }

      const confident = result.confidence >= CONFIDENCE_THRESHOLD;
      const hasCandidates = (result.candidates?.length ?? 0) > 0;
      const needsConfirm = !confident || hasCandidates;

      // 확실한 값만 반영한다. null 은 기존 선택을 덮어쓰지 않는다.
      if (result.fromNodeId) onFromChange(result.fromNodeId);
      if (result.toNodeId) onToChange(result.toNodeId);
      if (result.mode) onModeSuggest(result.mode);
      if (result.weather) onWeatherSuggest(result.weather);

      setParse({ kind: 'done', result, needsConfirm });
    },
    [fromNodeId, onFromChange, onToChange, onModeSuggest, onWeatherSuggest],
  );

  const chooseCandidate = (field: 'from' | 'to', nodeId: string) => {
    if (field === 'from') onFromChange(nodeId);
    else onToChange(nodeId);

    setParse((prev) => {
      if (prev.kind !== 'done') return prev;
      const remaining = (prev.result.candidates ?? []).filter((c) => c.field !== field);
      return {
        kind: 'done',
        result: { ...prev.result, candidates: remaining },
        needsConfirm: remaining.length > 0,
      };
    });
  };

  return (
    <div className="flex flex-col gap-3.5 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm">
      {/* 자연어 입력 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(text);
        }}
      >
        <label htmlFor="nl-input" className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <Sparkles className="size-3.5 text-blue-600" aria-hidden="true" />
          말로 검색
        </label>
        <div className="flex gap-2">
          <input
            id="nl-input"
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="예) 나 지금 북악관인데 다음 수업 조형관 가야 해"
            className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-[15px] text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
            aria-describedby="nl-help"
          />
          <button
            type="submit"
            disabled={parse.kind === 'pending' || text.trim().length === 0}
            className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-3.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500"
          >
            {parse.kind === 'pending' ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="size-4" aria-hidden="true" />
            )}
            <span className="sr-only sm:not-sr-only">찾기</span>
          </button>
        </div>
        <p id="nl-help" className="mt-1 text-xs text-slate-500">
          자연어가 안 되면 아래에서 직접 선택해도 됩니다.
        </p>
      </form>

      {/* 파싱 결과 피드백 */}
      {parse.kind === 'unavailable' && (
        <p className="rounded-xl bg-slate-100 px-3 py-2.5 text-[13px] font-medium text-slate-600">
          지금은 자연어 인식을 쓸 수 없습니다. 아래에서 출발지와 도착지를 직접 선택해 주세요.
        </p>
      )}

      {parse.kind === 'done' && (
        <div
          className={cn(
            'rounded-xl px-3 py-2.5',
            parse.needsConfirm ? 'bg-amber-50 ring-1 ring-amber-200' : 'bg-blue-50 ring-1 ring-blue-200',
          )}
        >
          <p
            className={cn(
              'text-[13px] font-medium',
              parse.needsConfirm ? 'text-amber-900' : 'text-blue-900',
            )}
          >
            {parse.result.reply}
          </p>

          {parse.result.mode && (
            <p className="mt-1 text-[12px] text-slate-600">
              이동 방식을 <strong>{TRAVEL_MODE_LABEL[parse.result.mode]}</strong> 으로 맞췄습니다.
            </p>
          )}

          {parse.needsConfirm && (parse.result.candidates?.length ?? 0) === 0 && (
            <p className="mt-1 text-[12px] text-amber-800">
              확신도가 낮습니다. 아래 선택이 맞는지 확인해 주세요.
            </p>
          )}

          {parse.result.candidates?.map((group) => (
            <div key={group.field} className="mt-2">
              <p className="mb-1 text-[12px] font-semibold text-slate-700">
                {group.field === 'from' ? '출발지' : '도착지'}가 어디인가요?
              </p>
              <div className="flex flex-wrap gap-1.5">
                {group.nodes.map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => chooseCandidate(group.field, node.id)}
                    className="min-h-11 rounded-full border border-slate-300 bg-white px-3 text-[13px] font-medium text-slate-800 transition hover:border-slate-500 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-blue-500"
                  >
                    {node.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <hr className="border-slate-200" />

      {/* 출발 / 도착 */}
      <div className="flex flex-col gap-2.5">
        <NodeCombobox
          label="출발"
          tone="from"
          nodes={nodes}
          value={fromNodeId}
          onChange={onFromChange}
          loading={nodesLoading}
          placeholder="지금 있는 곳"
        />

        <div className="flex justify-center">
          <button
            type="button"
            onClick={onSwap}
            disabled={!fromNodeId && !toNodeId}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3.5 text-[13px] font-semibold text-slate-700 transition hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-blue-500"
          >
            <ArrowUpDown className="size-4" aria-hidden="true" />
            출발·도착 바꾸기
          </button>
        </div>

        <NodeCombobox
          label="도착"
          tone="to"
          nodes={nodes}
          value={toNodeId}
          onChange={onToChange}
          loading={nodesLoading}
          placeholder="가려는 강의실"
        />
      </div>
    </div>
  );
}
