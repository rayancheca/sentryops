"use client";

import { QrCode } from "lucide-react";
import { useEffect, useState } from "react";

import { Spinner } from "@/components/ui";
import { API_BASE, getToken } from "@/lib/api";

export interface AssetQrProps {
  assetId: string;
  shortCode: string;
}

// The QR endpoint requires the bearer token, so a bare <img src> would 401.
// Fetch the SVG with auth and inline it (SVG is trusted, server-generated markup).
async function fetchQrSvg(assetId: string): Promise<string> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/assets/${assetId}/qr.svg`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`QR fetch failed (${res.status})`);
  return res.text();
}

export function AssetQr({ assetId, shortCode }: AssetQrProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setSvg(null);
    setFailed(false);
    fetchQrSvg(assetId)
      .then((markup) => {
        if (active) setSvg(markup);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [assetId]);

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="flex size-44 items-center justify-center rounded-md border border-border bg-text p-3 [&_svg]:h-full [&_svg]:w-full"
        aria-label={`QR label for ${shortCode}`}
      >
        {failed ? (
          <QrCode className="size-10 text-bg" aria-hidden="true" />
        ) : svg ? (
          // eslint-disable-next-line react/no-danger -- server-generated trusted SVG
          <span dangerouslySetInnerHTML={{ __html: svg }} />
        ) : (
          <Spinner label="Loading QR label" />
        )}
      </div>
      <span className="tabular text-sm text-accent">{shortCode}</span>
      {failed ? <span className="text-xs text-text-dim">QR label unavailable</span> : null}
    </div>
  );
}
