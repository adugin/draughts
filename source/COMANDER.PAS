unit comander;
interface
  const x0=8;
        y0=8;
        width=40;
        border=2;
  type chessboard=array[1..y0,1..x0] of char;
       {memory=array[1..3] of string[32];}
  procedure eraseall;
  function Maximum(x,y:byte):byte;
  function between(x,y:shortint):boolean;
  function FileExist(name:string;new:boolean):boolean;
  function search(name,searchtext:string):boolean;
  function invert(mas:chessboard):string;
  function invertstr(st:string):string;
  procedure Button(x1,y1,x2,y2:integer;text:string;permission:boolean);
  procedure InButton(x1,y1,x2,y2:integer;color:word);
  procedure mark(x,y:integer;color:byte);
  procedure Square(x,y:integer;color:word);
  procedure Draughtsman(x,y:integer;damka:boolean;color:word);
  procedure thunder;
implementation
  uses crt,mouse,graph,dos;
  var xm,ym:word;
      l,r,m:boolean;
{---------------------------------------------------------------------------}
procedure thunder;
var x,y:integer;
begin
  x:=getmaxx div 2;
  setcolor(yellow);
  for y:=0 to 240 do
  begin
    sound((240-y)*100);
    circle(x,y,1);
    x:=x+random(3)-1;
    delay(1);
  end;
  nosound;
  setbkcolor(lightgreen);
  cleardevice;
  delay(100);
  setbkcolor(black);
  cleardevice;
end;
{---------------------------------------------------------------------------}
procedure Draughtsman(x,y:integer;damka:boolean;color:word); {рисование шашки}
var r:byte;
begin
  r:=(width-4-border) div 2;
  mouseoff;
  setcolor(color);
  setlinestyle(0,0,1);
  setfillstyle(solidfill,color);
  sector(x,y,0,360,r,r);
  if color=white then setcolor(darkgray) else setcolor(lightgray);
  circle(x,y,r);
  if damka=false then
  begin
    circle(x,y,r-4);
    circle(x,y,r-8);
    if width>=50 then circle(x,y,r-12);
  end else
  begin
    setcolor(15-color);
    line(x-8,y+7,x+8,y+7);
    line(x-8,y+7,x-10,y-3);
    line(x+8,y+7,x+10,y-3);
    line(x-10,y-3,x-4,y+1);
    line(x+10,y-3,x+4,y+1);
    line(x-4,y+1,x,y-8);
    line(x+4,y+1,x,y-8);
    setfillstyle(solidfill,yellow);
    floodfill(x,y,15-color);
    setcolor(lightmagenta);
    circle(x,y+3,1);
    circle(x-5,y+4,1);
    circle(x+5,y+4,1);
  end;
  if color=black then setcolor(lightgray) else setcolor(white);
  setlinestyle(0,0,3);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure Square(x,y:integer;color:word); {рисование клетки поля}
begin
  setlinestyle(solidln,0,3);
  setcolor(black);
  mouseoff;
  rectangle(x*width,y*width,(x+1)*width,(y+1)*width);
  setfillstyle(solidfill,color);
  bar(x*width+border,y*width+border,(x+1)*width-border,(y+1)*width-border);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure mark(x,y:integer;color:byte);
begin
  setlinestyle(solidln,0,1);
  setcolor(color);
  mouseoff;
  line(x-3,y,x-1,y+3);
  line(x-1,y+3,x+3,y-2);
  line(x-3,y-1,x-1,y+2);
  line(x-1,y+2,x+3,y-3);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure Button(x1,y1,x2,y2:integer;text:string;permission:boolean);
          {прорисовка кнопки с надписью}
var n:integer;
begin
  if (abs(x2-x1)>textwidth(text))and(abs(y2-y1)>textheight(text))then
  begin
    mouseoff;
    setfillstyle(solidfill,lightgray);
    bar(x1,y1,x2,y2);
    setlinestyle(solidln,0,1);
    setcolor(white);
    line(x1+1,y1+1,x2-1,y1+1);
    line(x1+1,y1+1,x1+1,y2-1);
    if (text<>'X')and(text<>'Да')and(text<>'Нет') then
    begin
      line(x1+2,y1+2,x2-2,y1+2);
      line(x1+2,y1+2,x1+2,y2-2);
    end;
    setcolor(darkgray);
    line(x1+1,y2-1,x2-1,y2-1);
    line(x2-1,y1+1,x2-1,y2-1);
    if (text<>'X')and(text<>'Да')and(text<>'Нет') then
    begin
      line(x1+2,y2-2,x2-2,y2-2);
      line(x2-2,y1+2,x2-2,y2-2);
    end;
    setcolor(black);
    rectangle(x1,y1,x2,y2);
    settextjustify(1,1);
    if permission=false then
    begin
      setcolor(white);
      outtextxy((x1+x2) div 2+1,(y1+y2) div 2+2,text);
      setcolor(darkgray);
      outtextxy((x1+x2) div 2,(y1+y2) div 2+1,text);
    end else
    begin
      setcolor(black);
      outtextxy((x1+x2) div 2,(y1+y2) div 2+1,text);
    end;
  end;
  mouseon;
  settextjustify(0,1);
end; {ok}
{---------------------------------------------------------------------------}
procedure InButton(x1,y1,x2,y2:integer;color:word); {вдавленность}
begin
  setlinestyle(solidln,0,1);
  setcolor(darkgray);
  line(x1,y1,x1,y2);
  line(x1,y1,x2,y1);
  setcolor(white);
  line(x1,y2,x2,y2);
  line(x2,y1,x2,y2);
  setfillstyle(solidfill,color);
  bar(x1+1,y1+1,x2-1,y2-1);
end; {ok}

{---------------------------------------------------------------------------}
procedure eraseall; {удаление ненужных файлов}
var f:text;
begin
  {$I-}
  assign(f,'autosave.sav');
  rewrite(f);
  close(f);
  erase(f);
  assign(f,'movie.sav');
  rewrite(f);
  close(f);
  erase(f);
  {$I+}
end; {ok}
{---------------------------------------------------------------------------}
function Maximum(x,y:byte):byte; {поиск максимального радиуса внутри доски}
var max:byte;
    h:shortint;
begin
  max:=y0-y;
  h:=y-1;
  if h>max then max:=h;
  h:=x0-x;
  if h>max then max:=h;
  h:=x-1;
  if h>max then max:=h;
  maximum:=max;
end; {ok}

{---------------------------------------------------------------------------}
function between(x,y:shortint):boolean; {проверка диапазона}
begin
  between:=false;
  if x>=1 then
  if x<=x0 then
  if y>=1 then
  if y<=y0 then between:=true;
end; {ok}
{---------------------------------------------------------------------------}
function FileExist(name:string;new:boolean):boolean;
var f:text;
begin
  {$I-}
  assign(f,name);
  reset(f);
  if ioresult<>0 then
  begin
    if new then rewrite(f);
    fileexist:=false;
  end else
  fileexist:=true;
  close(f);
  {$I+}
end;
{---------------------------------------------------------------------------}
function search(name,searchtext:string):boolean;
var f:text;
    st:string;
begin
  search:=false;
    fileexist(name,true);
  assign(f,name);
  reset(f);
  while not eof(f) do
  begin
    readln(f,st);
    if st=searchtext then
    begin
      search:=true;
      close(f);
      exit;
    end;
  end;
  close(f);
end; {ok}
{---------------------------------------------------------------------------}
function invert(mas:chessboard):string;
var x,y:byte;
    st:string;
begin
  st:='';
  for y:=y0 downto 1 do
  for x:=x0 downto 1 do
  if (x mod 2<>y mod 2) then
  begin
    case mas[y,x] of 'b':st:=st+'w';
                     'B':st:=st+'W';
                     'w':st:=st+'b';
                     'W':st:=st+'B';
                     'n':st:=st+'n';
                  end;
  end;
  invert:=st;
end; {ok}
{---------------------------------------------------------------------------}
function invertstr(st:string):string;
var n:byte;
    s:string;
begin
  s:='';
  for n:=length(st) downto 1 do
  begin
    case st[n] of 'b':s:=s+'w';
                  'B':s:=s+'W';
                  'w':s:=s+'b';
                  'W':s:=s+'B';
                  'n':s:=s+'n';
               end;
  end;
  invertstr:=s;
end; {ok}
end.