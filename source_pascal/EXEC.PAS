{$M $4000,0,0 }
uses crt,dos;
begin
  textcolor(lightgreen);
  clrscr;
  writeln('Нажмите Enter...');
  readln;
  swapvectors;
  exec(getenv('comspec'),'c:\work\explorer\draughts\start.bat');
  swapvectors;
  exit;
end.