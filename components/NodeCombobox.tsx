'use client';

/**
 * 강의실/장소 선택 콤보박스.
 *
 * 접근성:
 *  - role="combobox" + aria-expanded / aria-controls / aria-activedescendant
 *  - 목록은 role="listbox", 항목은 role="option" + aria-selected
 *  - ↑ ↓ Home End 로 이동, Enter 로 선택, Esc 로 닫기
 *  - 터치 타깃 44px 이상 (min-h-11)
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import type { NodeSummary } from '@/lib/types';
import { filterNodes } from '@/lib/ui/useNodes';
import { formatPlace } from '@/lib/ui/theme';
import { cn } from '@/lib/ui/cn';

interface NodeComboboxProps {
  label: string;
  placeholder?: string;
  nodes: NodeSummary[];
  value: string | null;
  onChange: (nodeId: string | null) => void;
  loading?: boolean;
  /** 출발지는 초록, 도착지는 빨강 점으로 구분 */
  tone: 'from' | 'to';
}

export function NodeCombobox({
  label,
  placeholder = '건물 또는 강의실 검색',
  nodes,
  value,
  onChange,
  loading = false,
  tone,
}: NodeComboboxProps) {
  const reactId = useId();
  const listboxId = `${reactId}-listbox`;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selected = useMemo(
    () => (value ? nodes.find((n) => n.id === value) ?? null : null),
    [nodes, value],
  );

  const options = useMemo(
    () => filterNodes(nodes, open ? query : '', 50),
    [nodes, open, query],
  );

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
  }, []);

  const commit = useCallback(
    (node: NodeSummary) => {
      onChange(node.id);
      close();
      inputRef.current?.focus();
    },
    [onChange, close],
  );

  // 바깥 클릭 시 닫기
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open, close]);

  // 활성 항목을 보이는 영역으로
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [open, activeIndex]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveIndex(0);
        return;
      }
      if (options.length === 0) return;
      const dir = e.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex((i) => (i + dir + options.length) % options.length);
      return;
    }
    if (e.key === 'Home' && open) {
      e.preventDefault();
      setActiveIndex(0);
      return;
    }
    if (e.key === 'End' && open) {
      e.preventDefault();
      setActiveIndex(Math.max(0, options.length - 1));
      return;
    }
    if (e.key === 'Enter') {
      if (open && options[activeIndex]) {
        e.preventDefault();
        commit(options[activeIndex]);
      }
      return;
    }
    if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        close();
      }
      return;
    }
    if (e.key === 'Tab' && open) {
      close();
    }
  };

  const dotClass = tone === 'from' ? 'bg-emerald-500' : 'bg-rose-500';

  return (
    <div
      ref={wrapperRef}
      className="relative"
      onBlur={(e) => {
        if (!wrapperRef.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      <label
        htmlFor={`${reactId}-input`}
        className="mb-1 flex items-center gap-2 text-sm font-semibold text-slate-700"
      >
        <span className={cn('inline-block size-2.5 shrink-0 rounded-full', dotClass)} aria-hidden="true" />
        {label}
      </label>

      <div
        className={cn(
          'flex items-center gap-2 rounded-xl border bg-white px-3 transition',
          open ? 'border-blue-500 ring-2 ring-blue-200' : 'border-slate-300 hover:border-slate-400',
        )}
      >
        <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <input
          ref={inputRef}
          id={`${reactId}-input`}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open && options[activeIndex] ? `${reactId}-opt-${activeIndex}` : undefined}
          aria-describedby={`${reactId}-hint`}
          className="min-h-11 w-full bg-transparent py-2 text-[15px] text-slate-900 outline-none placeholder:text-slate-400"
          placeholder={loading ? '장소 목록 불러오는 중…' : placeholder}
          value={open ? query : selected?.label ?? ''}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActiveIndex(0);
          }}
          onFocus={() => {
            setOpen(true);
            setQuery('');
            setActiveIndex(0);
          }}
          onKeyDown={onKeyDown}
          disabled={loading}
        />

        {selected && !open && (
          <button
            type="button"
            onClick={() => {
              onChange(null);
              inputRef.current?.focus();
            }}
            className="grid size-11 shrink-0 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            aria-label={`${label} 선택 지우기`}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        )}

        <ChevronDown
          className={cn('size-4 shrink-0 text-slate-400 transition-transform', open && 'rotate-180')}
          aria-hidden="true"
        />
      </div>

      <p id={`${reactId}-hint`} className="sr-only">
        위아래 방향키로 목록을 이동하고 엔터로 선택합니다. 강의실 번호나 건물명으로 검색할 수 있습니다.
      </p>

      {open && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-label={`${label} 후보`}
          className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white py-1 shadow-xl"
        >
          {options.length === 0 && (
            <li className="px-3 py-3 text-sm text-slate-500" role="presentation">
              검색 결과가 없습니다. 건물명이나 강의실 번호로 다시 검색해 보세요.
            </li>
          )}

          {options.map((node, index) => {
            const isActive = index === activeIndex;
            const isSelected = node.id === value;
            return (
              <li
                key={node.id}
                id={`${reactId}-opt-${index}`}
                role="option"
                aria-selected={isSelected}
                onPointerDown={(e) => e.preventDefault()}
                onClick={() => commit(node)}
                onMouseEnter={() => setActiveIndex(index)}
                className={cn(
                  'flex min-h-11 cursor-pointer items-center justify-between gap-3 px-3 py-2 text-[15px]',
                  isActive ? 'bg-blue-50 text-blue-900' : 'text-slate-800',
                )}
              >
                <span className="flex min-w-0 flex-col">
                  <span className="truncate font-medium">{node.label}</span>
                  <span className="truncate text-xs text-slate-500">
                    {formatPlace(node.building, node.floor)}
                  </span>
                </span>
                {isSelected && <Check className="size-4 shrink-0 text-blue-600" aria-hidden="true" />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
