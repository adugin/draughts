{ ============================================================================ }
{ EXEC.PAS -- Launcher/wrapper for the Draughts game                           }
{                                                                              }
{ Bootstrap loader that displays "Press Enter..." (CP866 Russian), waits for   }
{ input, then shells out to run start.bat via COMSPEC. Uses the standard       }
{ Borland Pascal SwapVectors/Exec pattern for launching child processes.       }
{ ============================================================================ }

{ Memory: 16KB stack, no heap -- this program only launches another }

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