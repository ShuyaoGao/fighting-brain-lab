// 无画面对打测试：node test_core.js [局数]
const C = require('./core.js');
const N = +process.argv[2] || 4;

function lcg(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// 套路玩家（模拟会几招就嘴硬的人）
const BOTS = {
  jabSpam: () => { let t = 0; return g => ({ h: 1, v: 0, atk: (t++ % 6 === 0) ? 'jab' : '' }); },
  fireball: () => { let t = 0; return g => ({ h: -1, v: 0, atk: (t++ % 20 === 0) ? 'fbB' : '' }); },
  dpSpam: () => { let t = 0; return g => ({ h: -1, v: -1, atk: (t++ % 25 === 0) ? 'dpB' : '' }); },
  jumpIn: i => { let t = 0; return g => { const f = g.f[i]; t++; if (f.st === 'air') return { h: 0, v: 0, atk: f.vy < 2 ? 'jB' : '' }; return { h: 1, v: t % 30 === 0 ? 1 : 0, atk: '' }; }; },
  mash: () => { const r = lcg(7); const atks = ['jab', 'heavy', 'cA', 'cB', 'over', 'fbA', 'dpA', 'throw', '']; return g => ({ h: Math.floor(r() * 3) - 1, v: r() < 0.1 ? 1 : r() < 0.2 ? -1 : 0, atk: r() < 0.3 ? atks[Math.floor(r() * atks.length)] : '' }); },
  turtle: () => { let t = 0; return g => ({ h: -1, v: (t++ % 40 < 20) ? -1 : 0, atk: t % 45 === 0 ? 'cA' : '' }); },
};

function play(mk0, mk1, rounds, seed) {
  let w = [0, 0, 0], hpLeft = [0, 0], ms = 0, frames = 0;
  for (let r = 0; r < rounds; r++) {
    const g = C.newGame({ silent: true });
    const p0 = mk0(0, seed + r), p1 = mk1(1, seed * 7 + r);
    while (!g.over && g.t < 70 * 60) {
      const t0 = process.hrtime.bigint();
      const a = p0(g), b = p1(g);
      ms += Number(process.hrtime.bigint() - t0) / 1e6;
      C.step(g, a, b);
      frames++;
    }
    w[g.winner < 0 ? 2 : g.winner]++;
    hpLeft[0] += g.f[0].hp; hpLeft[1] += g.f[1].hp;
  }
  return { w, hpLeft: hpLeft.map(h => Math.round(h / rounds)), msPerFrame: +(ms / frames).toFixed(3) };
}

const ai = lvl => (i, seed) => { const a = C.makeAI(lvl, i, seed); return g => a.intent(g); };
const bot = name => (i) => BOTS[name](i);

console.log(`每组 ${N} 回合；w=[左胜,右胜,平]，hp=平均剩余血量（满 1000），ms=AI 每帧平均耗时`);
for (const b of Object.keys(BOTS)) {
  for (const lvl of ['normal', 'god']) {
    const r = play(ai(lvl), bot(b), N, 11);
    console.log(`${lvl.padEnd(6)} vs ${b.padEnd(9)} w=${r.w} hp=${r.hpLeft} ms=${r.msPerFrame}`);
  }
}
for (const [a, b] of [['god', 'hard'], ['god', 'normal'], ['hard', 'normal'], ['normal', 'easy']]) {
  const r1 = play(ai(a), ai(b), N, 3), r2 = play(ai(b), ai(a), N, 5);
  console.log(`${a} vs ${b}: ${a} 胜 ${r1.w[0] + r2.w[1]} / ${b} 胜 ${r1.w[1] + r2.w[0]} / 平 ${r1.w[2] + r2.w[2]}  ms=${r1.msPerFrame}`);
}
