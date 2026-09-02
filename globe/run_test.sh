#!/bin/bash
# Timed, resource-capped render with peak-RSS sampling. Env: N MB SS Wpx Q
cd ~/globe-service || exit 1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export N=${N:-1080} MB=${MB:-1} SS=${SS:-2} Wpx=${Wpx:-440} Q=${Q:-56} EXTRA=0
export OUT="$HOME/globe-service/work/globe_test.avif"
mkdir -p work
start=$(date +%s)
nice -n 19 ionice -c3 ./venv/bin/python build_earth.py > work/render.log 2>&1 &
PID=$!
echo 800 > "/proc/$PID/oom_score_adj" 2>/dev/null   # make the render the first OOM victim, not other services
peak=0
while kill -0 "$PID" 2>/dev/null; do
  rss=$(awk '/VmRSS/{print $2}' "/proc/$PID/status" 2>/dev/null)
  [ -n "$rss" ] && [ "$rss" -gt "$peak" ] && peak=$rss
  sleep 3
done
wait "$PID"; rc=$?
echo "=== RESULT exit=$rc  elapsed=$(( $(date +%s)-start ))s  peakRSS=$((peak/1024))MB  (N=$N Wpx=$Wpx) ==="
tail -4 work/render.log
ls -la "$OUT" 2>/dev/null | awk '{print "output:",$5,"bytes",$9}'
