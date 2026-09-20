'use client';

/**
 * 시간표 이미지 업로드 → 다음 수업 강의실 자동 인식.
 *
 * 엔진(OCR/Vision)이 강의실 매칭에 실패하면 nodeId 가 null 로 온다.
 * 그때는 추측하지 않고 사용자가 직접 고르게 한다.
 *
 * 접근성: 드롭존은 label + 시각적으로 숨긴 file input 으로 만들어
 *         마우스 없이 Tab + Enter 로도 파일을 선택할 수 있다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Clock, Loader2, Trash2, Upload } from 'lucide-react';
import { uploadTimetable } from '@/lib/client';
import type { NodeSummary, TimetableResult } from '@/lib/types';
import { NodeCombobox } from './NodeCombobox';
import { cn } from '@/lib/ui/cn';

interface TimetableUploadProps {
  nodes: NodeSummary[];
  nodesLoading: boolean;
  onPickDestination: (nodeId: string) => void;
}

type UploadState = 'idle' | 'uploading' | 'done' | 'failed';

export function TimetableUpload({ nodes, nodesLoading, onPickDestination }: TimetableUploadProps) {
  const [state, setState] = useState<UploadState>('idle');
  const [result, setResult] = useState<TimetableResult | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  /** OCR 이 강의실을 못 찾은 과목에 사용자가 직접 지정한 노드 */
  const [manual, setManual] = useState<Record<number, string>>({});
  const previewRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) {
      setState('failed');
      setResult(null);
      return;
    }

    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const url = URL.createObjectURL(file);
    previewRef.current = url;
    setPreview(url);
    setManual({});
    setState('uploading');

    const res = await uploadTimetable(file);
    if (!res) {
      setState('failed');
      setResult(null);
      return;
    }
    setResult(res);
    setState('done');
  }, []);

  const reset = () => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    setPreview(null);
    setResult(null);
    setManual({});
    setState('idle');
  };

  const nextCourse =
    result?.next != null ? result.courses[result.next.courseIndex] ?? null : null;
  const nextNodeId =
    result?.next != null
      ? nextCourse?.nodeId ?? manual[result.next.courseIndex] ?? null
      : null;

  return (
    <section aria-labelledby="timetable-heading" className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h2 id="timetable-heading" className="text-sm font-semibold text-slate-700">
          시간표로 다음 수업 찾기
        </h2>
        {state !== 'idle' && (
          <button
            type="button"
            onClick={reset}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
            초기화
          </button>
        )}
      </div>

      {/* 드롭존 */}
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        className={cn(
          'flex min-h-[88px] cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed p-4 text-center transition',
          'focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-200',
          dragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-slate-50 hover:border-slate-400',
        )}
      >
        <input
          type="file"
          accept="image/*"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = '';
          }}
        />
        {state === 'uploading' ? (
          <>
            <Loader2 className="size-5 animate-spin text-blue-600" aria-hidden="true" />
            <span className="text-[13px] font-medium text-slate-600">시간표를 읽는 중…</span>
          </>
        ) : (
          <>
            <Upload className="size-5 text-slate-400" aria-hidden="true" />
            <span className="text-[13px] font-medium text-slate-700">
              시간표 이미지를 끌어다 놓거나 클릭해서 선택
            </span>
            <span className="text-[11px] text-slate-500">PNG · JPG · 스크린샷</span>
          </>
        )}
      </label>

      {preview && (
        <div className="mt-2.5 overflow-hidden rounded-xl border border-slate-200">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={preview} alt="업로드한 시간표 미리보기" className="max-h-40 w-full object-contain bg-slate-50" />
        </div>
      )}

      {state === 'failed' && (
        <p className="mt-2.5 rounded-xl bg-rose-50 px-3 py-2.5 text-[13px] font-medium text-rose-800">
          시간표를 읽지 못했습니다. 다른 이미지로 다시 시도하거나 위에서 강의실을 직접 선택해 주세요.
        </p>
      )}

      {/* 다음 수업 */}
      {state === 'done' && result?.next && (
        <div className="mt-2.5 rounded-xl border border-blue-200 bg-blue-50 p-3">
          <p className="flex items-center gap-1.5 text-[13px] font-bold text-blue-900">
            <Clock className="size-4" aria-hidden="true" />
            {result.next.message}
          </p>
          {nextCourse && (
            <p className="mt-1 text-[12px] text-blue-800">
              {nextCourse.title} · {nextCourse.roomLabel} · {nextCourse.startsAt}
            </p>
          )}
          <button
            type="button"
            disabled={!nextNodeId}
            onClick={() => nextNodeId && onPickDestination(nextNodeId)}
            className="mt-2.5 inline-flex min-h-11 items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500"
          >
            이 강의실까지 경로 보기
          </button>
          {!nextNodeId && (
            <p className="mt-1.5 text-[12px] font-medium text-amber-800">
              강의실을 지도에서 찾지 못했습니다. 아래에서 직접 지정해 주세요.
            </p>
          )}
        </div>
      )}

      {/* 과목 목록 */}
      {state === 'done' && result && result.courses.length > 0 && (
        <ul className="mt-2.5 flex flex-col gap-1.5">
          {result.courses.map((course, index) => {
            const resolved = course.nodeId ?? manual[index] ?? null;
            return (
              <li
                key={`${course.title}-${index}`}
                className="rounded-xl border border-slate-200 p-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold text-slate-900">{course.title}</p>
                    <p className="text-[12px] text-slate-500">
                      {course.day} {course.startsAt}–{course.endsAt} · {course.roomLabel}
                    </p>
                  </div>
                  {resolved ? (
                    <button
                      type="button"
                      onClick={() => onPickDestination(resolved)}
                      className="min-h-11 shrink-0 rounded-lg border border-slate-300 px-2.5 text-[12px] font-semibold text-slate-700 transition hover:border-slate-500 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      도착지로
                    </button>
                  ) : (
                    <span className="shrink-0 rounded-lg bg-amber-100 px-2 py-1 text-[11px] font-bold text-amber-800">
                      매칭 실패
                    </span>
                  )}
                </div>

                {!course.nodeId && (
                  <div className="mt-2">
                    <NodeCombobox
                      label="강의실 직접 지정"
                      tone="to"
                      nodes={nodes}
                      value={manual[index] ?? null}
                      onChange={(id) =>
                        setManual((prev) => {
                          const next = { ...prev };
                          if (id) next[index] = id;
                          else delete next[index];
                          return next;
                        })
                      }
                      loading={nodesLoading}
                      placeholder={`"${course.roomLabel}" 에 해당하는 곳`}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
