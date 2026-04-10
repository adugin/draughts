{$A+,B-,D+,E+,F-,G-,I-,L+,N-,O-,P-,Q-,R-,S+,T-,V+,X+}
{$M 65520,0,655360}
uses crt,graph,mouse,comander,dos;
type alphabet=set of 'A'..'z';
const whites:alphabet=['w','W'];
      blacks:alphabet=['b','B'];
      damkas:alphabet=['W','B'];
      x0=10;
      y0=10;
      width=40;
      border=2;
      NeedToSave=1;
      depth0=1;
      maxrnd=1000;
      digits:array[1..y0] of char='87654321';
      abc:array[1..x0] of char='abcdefgh';
      cursor=lightmagenta;
      dir:array [1..4,1..2] of shortint=((-1,1),(1,1),(1,-1),(-1,-1));
      stroka0=9;
type chessboard=array[1..y0,1..x0] of char;
     variants=array[0..6,1..2] of shortint;
     memory=array[1..3] of string[32];
var model,field,whitefield,blackfield:chessboard;
    score,maxscore:shortint;
    try,optimum:variants;
    whitestr,blackstr,helpstr:memory;
    place:array[1..2,0..5] of integer;
    xx,yy,a,c,d,x,y,x1,y1,x2,y2,xc,yc,xb,yb,xw,yw,
      num,num0,w,b,stroka,beat_w,beat_b,size1,size2,dx,dy,period,timenow,wsize:integer;
    ch:char;
    beat,hod,l,r,m,permission,ok,soundeffect,next1,next2,remind,mustbeat,
      startgame,contin,opportunity,endofgame,whiteaction,blackaction,blacklose,
      blackwin,whitelose,whitewin,usebase,invertcolor,newboard,damka:boolean;
    st,st1,st2,st3,TimeString,filename,lastfilename,timeleft,msg:string;
    situation:integer;
    f:text;
    n1,n2,bx,by,radius,depth:byte;
    xm,ym,xm0,ym0,lastcolor:word;
    p1,p2,boardview,shirm,wp:pointer;
    difficulty,speed,language:byte;
    pause:real;
    hour,minute,second,sec100:word;
{---------------------------------------------------------------------------}
function commander:boolean;forward;
{---------------------------------------------------------------------------}
function dcolor(x,y:byte;mas:chessboard):byte;
begin
  if mas[y,x] in blacks then dcolor:=black else
  if mas[y,x] in whites then dcolor:=white;
end;
{---------------------------------------------------------------------------}
function getcolor(color:byte):byte;
begin
  if invertcolor=true then
  begin
    case color of white:getcolor:=black;
                  black:getcolor:=white;
               end;
  end else
  getcolor:=color;
end; {ok}
{---------------------------------------------------------------------------}
function GetString(mas:chessboard):string;
var x,y:byte;
    st:string;
begin
  st:='';
  for y:=1 to y0 do
  for x:=1 to x0 do
  if (x mod 2<>y mod 2) then
    st:=st+mas[y,x];
  getstring:=st;
end; {ok}
{---------------------------------------------------------------------------}
procedure roll(var memorystr:memory;newstr:string);
begin
  memorystr[1]:=memorystr[2];
  memorystr[2]:=memorystr[3];
  memorystr[3]:=newstr;
end; {ok}
{---------------------------------------------------------------------------}
procedure SaveCombination(mas:memory;name:string);
var f:text;
    n:byte;
    present:array[1..3] of boolean;
    st:string;
    done:boolean;
begin
  done:=false;
  for n:=1 to 3 do present[n]:=false;
  fileexist(name,true);
  assign(f,name);
  reset(f);
  while not eof(f) do
  begin
    readln(f,st);
    for n:=1 to 3 do
      if st=mas[n] then present[n]:=true;
  end;
  close(f);
  append(f);
  for n:=1 to 3 do
  if (present[n]=false)and(mas[n]<>'') then
  begin
    writeln(f,mas[n]);
    done:=true;
  end;
  close(f);
end; {ok}
{---------------------------------------------------------------------------}
function appreciate(mas1,mas2:chessboard;color:byte):shortint;
var x,y:integer;
    score,k:shortint;
begin
  score:=0;
  if color=white then k:=1 else
  if color=black then k:=-1 else
                      k:=0;
  for y:=1 to y0 do
  for x:=1 to x0 do
  begin
    case mas1[y,x] of 'b':score:=score+k;
                      'w':score:=score-k;
                      'B':score:=score+2*k;
                      'W':score:=score-2*k;
                   end;
    case mas2[y,x] of 'b':score:=score-k;
                      'w':score:=score+k;
                      'B':score:=score-2*k;
                      'W':score:=score+2*k;
                   end;
  end;
  appreciate:=score;
end; {ok}
{---------------------------------------------------------------------------}
Procedure VertWait;far;Assembler; {возврат луча}
Asm
   mov dx,03dah
@@vwl1:
   in  al,dx
   test al,8
   jz @@vwl1
@@vwl2:
   in  al,dx
   test al,8
   jnz @@vwl2
End; {ok}
{---------------------------------------------------------------------------}
procedure disappear; {подготовка "ширмы" для доски}
var size:integer;
    x,y:integer;
begin
  randomize;
  setactivepage(1);
  for x:=0 to x0*width do
  for y:=0 to y0*width do
   if (random(6)<>0) then
     putpixel(x,y,random(15)+1);
  size:=imagesize(0,0,x0*width,y0*width);
  getmem(shirm,size);
  getimage(0,0,x0*width,y0*width,shirm^);
  setactivepage(0);
end; {ok}
{---------------------------------------------------------------------------}
procedure BoardOff; {скрытие доски}
const colors:array[0..2] of word=(darkgray,lightgray,white);
var size:integer;
begin
  size:=imagesize(width,width,(x0+1)*width,(y0+1)*width);
  getmem(boardview,size);
  mouseoff;
  getimage(width,width,(x0+1)*width,(y0+1)*width,boardview^);
  if shirm<>nil then putimage(width,width,shirm^,xorput);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure BoardOn; {открытие доски}
var size:integer;
begin
  size:=imagesize(width,width,(x0+1)*width,(y0+1)*width);
  mouseoff;
  putimage(width,width,boardview^,normalput);
  mouseon;
  freemem(boardview,size);
end; {ok}
{---------------------------------------------------------------------------}
procedure ButtonPress(x1,y1,x2,y2:integer;text:string); {нажатие кнопки}
var n:integer;
begin
  if (abs(x2-x1)>textwidth(text))and(abs(y2-y1)>textheight(text))then
  begin
    mouseoff;
    setfillstyle(solidfill,lightgray);
    bar(x1,y1,x2,y2);
    setlinestyle(solidln,0,1);
    setcolor(white);
    line(x1+1,y2-1,x2-1,y2-1);
    line(x2-1,y1+1,x2-1,y2-1);
    if (text<>'X')and(text<>'Да')and(text<>'Нет')and(text<>'Yes')and(text<>'No') then
    begin
      line(x1+2,y2-2,x2-2,y2-2);
      line(x2-2,y1+2,x2-2,y2-2);
    end;
    setcolor(darkgray);
    line(x1+1,y1+1,x2-1,y1+1);
    line(x1+1,y1+1,x1+1,y2-1);
    if (text<>'X')and(text<>'Да')and(text<>'Нет') then
    begin
      line(x1+2,y1+2,x2-2,y1+2);
      line(x1+2,y1+2,x1+2,y2-2);
    end;
    setcolor(black);
    rectangle(x1,y1,x2,y2);
    settextjustify(1,1);
    setcolor(black);
    outtextxy((x1+x2) div 2,(y1+y2) div 2+2,text);
    setmousexy(xm,ym+1);
    mouseon;
    while (l=true)and(xm>=x1)and(xm<=x2)and(ym>=y1)and(ym<=y2) do getmouseinfo(xm,ym,l,r,m);
    mouseoff;
    button(x1,y1,x2,y2,text,true);
    setmousexy(xm,ym-1);
    mouseon;
    delay(round(500*pause));
  end;
  gettime(hour,minute,second,sec100);
end; {ok}
{---------------------------------------------------------------------------}
procedure window(x,y,width,height:integer;text:string;off:boolean); {диалоговое окно}
const border=3;
      d=16;
var dx,dy:integer;
    n:integer;
begin
  mouseoff;
  if off then boardoff;
  wsize:=imagesize(x,y,x+width,y+height);
  getmem(wp,wsize);
  getimage(x,y,x+width,y+height,wp^);
  setcolor(lightgray);
  for n:=2 to width-2 do
  begin
    rectangle(x+(width-n) div 2,y+(height-round(n*height/width)) div 2,
              x+(width+n) div 2,y+(height+round(n*height/width)) div 2);
    delay(round(1.5*pause));
  end;
  button(x,y,x+width,y+height,'',true);
  setfillstyle(solidfill,blue);
  bar(x+border,y+border,x+width-border,y+border+d);
  button(x+width-border-15,y+border+2,x+width-border-1,y+border+15,'X',true);
  settextjustify(0,1);
  setcolor(white);
  outtextxy(x+border+5,y+border+d div 2,text);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure WindowOff(x,y:integer;off:boolean);
begin
  mouseoff;
  putimage(x,y,wp^,normalput);
  if off then boardon;
  mouseon;
  freemem(wp,wsize);
end; {ok}
{---------------------------------------------------------------------------}
procedure Message;
var x,y:integer;
begin
  x1:=274-textwidth(msg) div 2-10;
  y1:=443-36;
  window(x1,y1,textwidth(msg)+20,46,'Сообщение',false);
  settextjustify(1,1);
  setcolor(black);
  mouseoff;
  outtextxy(274,443-4,msg);
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
function OnceAgain(score:byte):boolean; {сообщение об исходе игры}
const width=200;
      height=85;
      border=3;
      buttonheight=14;
      buttonwidth=55;
      d=16;
var dx,dy,size,x11,y11,x12,y12,x21,y21,x22,y22:integer;
    p:pointer;
    lastcolor:word;
    ch:char;
    permission:boolean;
    st:string;
    n:byte;
begin
  delay(round(5000*pause));
  case score of 0:st:='Вы проиграли...';
                1:st:='Вы выиграли!'
             end;
  onceagain:=false;
  endofgame:=false;
  permission:=false;
  randomize;
  dx:=(getmaxx-width) div 2;
  dy:=(getmaxy-height) div 2;;
  mouseoff;
  window(dx,dy,width,height,'Внимание!',true);
  settextjustify(1,1);
  setcolor(black);
  outtextxy(dx+width div 2,dy+d+border+10,st);
  st:='Хотите сыграть еще раз?';
  outtextxy(dx+width div 2,dy+d+border+10+2*textheight(st),st);
  x11:=dx+(width-2*buttonwidth) div 3;
  y11:=dy+height-border-10-buttonheight;
  x12:=dx+(width-2*buttonwidth) div 3+buttonwidth;
  y12:=dy+height-border-5;
  x21:=dx+2*(width-2*buttonwidth) div 3+buttonwidth;
  y21:=dy+height-border-10-buttonheight;
  x22:=dx+2*(width-2*buttonwidth) div 3+2*buttonwidth;
  y22:=dy+height-border-5;
  button(x11,y11,x12,y12,'Да',true);
  button(x21,y21,x22,y22,'Нет',true);
  mouseon;
  repeat
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if l=true then
    begin
      if (xm>x11)and(ym>y11)and(xm<x12)and(ym<y12) then
      begin
        endofgame:=false;
        onceagain:=true;
        permission:=true;
        buttonpress(x11,y11,x12,y12,'Да');
      end else
      if (xm>x21)and(ym>y21)and(xm<x22)and(ym<y22) then
      begin
        endofgame:=true;
        permission:=true;
        buttonpress(x21,y21,x22,y22,'Нет');
      end else
      if (xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15) then
      begin
        endofgame:=true;
        permission:=true;
        buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      end;
    end;
  until permission=true;
  delay(round(3000*pause));
  windowoff(dx,dy,true);
end; {ok}
{---------------------------------------------------------------------------}
function Escape:boolean; {подтверждение выхода из игры}
const width=150;
      height=65;
      border=3;
      buttonheight=14;
      buttonwidth=55;
      d=16;
var dx,dy,size,x11,y11,x12,y12,x21,y21,x22,y22:integer;
    p:pointer;
    lastcolor:word;
    ch:char;
    permission:boolean;
    st:string;
    n:integer;
begin
  escape:=false;
  permission:=false;
  randomize;
  dx:=(getmaxx-width) div 2;
  dy:=(getmaxy-height) div 2;;
  mouseoff;
  window(dx,dy,width,height,'Выход',true);
  settextjustify(1,1);
  setcolor(black);
  st:='Выйти из игры?';
  outtextxy(dx+width div 2,dy+d+border+10,st);
  x11:=dx+(width-2*buttonwidth) div 3;
  y11:=dy+height-border-10-buttonheight;
  x12:=dx+(width-2*buttonwidth) div 3+buttonwidth;
  y12:=dy+height-border-5;
  x21:=dx+2*(width-2*buttonwidth) div 3+buttonwidth;
  y21:=dy+height-border-10-buttonheight;
  x22:=dx+2*(width-2*buttonwidth) div 3+2*buttonwidth;
  y22:=dy+height-border-5;
  button(x11,y11,x12,y12,'Да',true);
  button(x21,y21,x22,y22,'Нет',true);
  mouseon;
  repeat
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if l=true then
    begin
      if (xm>x11)and(ym>y11)and(xm<x12)and(ym<y12) then
      begin
        Escape:=true;
        permission:=true;
        buttonpress(x11,y11,x12,y12,'Да');
      end else
      if (xm>x21)and(ym>y21)and(xm<x22)and(ym<y22) then
      begin
        permission:=true;
        buttonpress(x21,y21,x22,y22,'Нет');
      end else
      if (xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15) then
      begin
        permission:=true;
        buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      end;
    end;
  until permission=true;
  windowoff(dx,dy,true);
end; {ok}
{---------------------------------------------------------------------------}
procedure Developement(x0,y0:word);
const width=180;
      height=86;
      border=3;
      count=4;
      mas:array[1..4] of string=('выигрыш компьютера','выигрыш игрока','проигрыш компьютера','проигрыш игрока');
var dx,dy,y,y1:integer;
    n,k,color,c,lc:byte;
    colors:array[1..count] of boolean;
begin
  for n:=1 to count do colors[n]:=false;
  dx:=x0-width-random(20);
  dy:=y0-random(20)+10;
  window(dx,dy,width,height,'Предмет анализа',true);
  mouseoff;
  settextjustify(0,1);
  for n:=1 to 4 do
  begin
    y:=dy+21+round((n-0.5)*(height-26)/4);
    inbutton(dx+6,y-4,dx+14,y+4,white);
    setcolor(black);
    outtextxy(dx+20,y,mas[n]);
    case n of 1:begin
                  case blackwin of true:color:=black;
                                   false:color:=white;
                                end;
                  mark(dx+10,y,color);
                end;
              2:begin
                  case whitewin of true:color:=black;
                                   false:color:=white;
                                end;
                  mark(dx+10,y,color);
                end;
              3:begin
                  case blacklose of true:color:=black;
                                    false:color:=white;
                                 end;
                  mark(dx+10,y,color);
                end;
              4:begin
                  case whitelose of true:color:=black;
                                    false:color:=white;
                                 end;
                  mark(dx+10,y,color);
                end;
           end;
  end;
  mouseon;
  lc:=black;
  repeat
    {if commander=false then getmouseinfo(xm,ym,l,r,m);}
    repeat
      l:=false;
      {if commander=false then} getmouseinfo(xm,ym,l,r,m);
      for n:=1 to 4 do
      begin
        y:=dy+21+round((n-0.5)*(height-26)/4);
        if (xm>=dx+6)and(ym>=y-4)and(xm<=dx+20+textwidth(mas[n]))and(ym<=y+4) then
        begin
          if colors[n]=false then
          begin
            colors[n]:=true;
            setcolor(yellow);
            mouseoff;
            outtextxy(dx+20,y,mas[n]);
            mouseon;
          end;
        end else
        if colors[n]=true then
        begin
          colors[n]:=false;
          setcolor(black);
          mouseoff;
          outtextxy(dx+20,y,mas[n]);
          mouseon;
        end;
      end;
    until l=true;
    for n:=1 to 4 do
    begin
      y:=dy+21+round((n-0.5)*(height-26)/4);
      if (xm>=dx+6)and(ym>=y-4)and(xm<=dx+20+textwidth(mas[n]))and(ym<=y+4) then
      begin
        repeat
          getmouseinfo(xm,ym,l,r,m);
          for k:=1 to 4 do
          begin
            y1:=dy+21+round((k-0.5)*(height-26)/4);
            if (xm>=dx+6)and(ym>=y1-4)and(xm<=dx+20+textwidth(mas[k]))and(ym<=y1+4) then
            begin
              if colors[k]=false then
              begin
                colors[k]:=true;
                setcolor(yellow);
                mouseoff;
                outtextxy(dx+20,y1,mas[k]);
                mouseon;
              end;
            end else
            if colors[k]=true then
            begin
              colors[k]:=false;
              setcolor(black);
              mouseoff;
              outtextxy(dx+20,y1,mas[k]);
              mouseon;
            end;
          end;
        until l=false;
        case n of 1:begin
                      case blackwin of true:color:=white;
                                       false:color:=black;
                                    end;
                      mark(dx+10,y,color);
                      blackwin:=not(blackwin);
                    end;
                  2:begin
                      case whitewin of true:color:=white;
                                       false:color:=black;
                                    end;
                      mark(dx+10,y,color);
                      whitewin:=not(whitewin);
                    end;
                  3:begin
                      case blacklose of true:color:=white;
                                        false:color:=black;
                                     end;
                      mark(dx+10,y,color);
                      blacklose:=not(blacklose);
                    end;
                  4:begin
                      case whitelose of true:color:=white;
                                        false:color:=black;
                                     end;
                      mark(dx+10,y,color);
                      whitelose:=not(whitelose);
                    end;
               end;
      end;
      {inbutton(dx+7,y-3,dx+13,y+3,white);
      setcolor(black);
      outtextxy(dx+20,y,mas[n]);}
    end;
  until (l=true)and(xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15);
  buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
  windowoff(dx,dy,true);
end; {ok}
{---------------------------------------------------------------------------}
procedure Options(x0,y0:word); {вызов меню опций}
label lb;
const width=212{225};
      buttonheight=17;
      buttonwidth=70;
      height=160+15+buttonheight;
      d=16;
      st1='сложность:';
      st2='скорость';
      st3='зафук:';
      st4='язык:';
      st5='звук:';
      st6='задержка:';
      st7='опыт:';
      st8='цвет:';
      count=8;
      mas:array [1..count] of string=(st1,st2,st3,st4,st5,st6,st7,st8);
      st='Опции';
      border=3;
      k=0.6;
      difficulties:array [1..3] of string=('новичок','мастер','профессионал');
      speeds:array [1..3] of string=('низкая','средняя','высокая');
      languages:array [1..2] of string=('русский','английский');
var p:pointer;
    x,y,size,n,xm0,ym0,px,py,i,code,x11,x12,x21,x22,y11,y12,y21,y22:integer;
    s:string;
    ch:char;
    pixel:boolean;
    difficulty1,speed1,language1,period1:byte;
    remind1,soundeffect1,invertcolor1,usebase1:boolean;
    pause1:real;
    filename1:string;
begin
  newboard:=false;
  difficulty1:=difficulty;
  speed1:=speed;
  language1:=language;
  period1:=period;
  remind1:=remind;
  soundeffect1:=soundeffect;
  invertcolor1:=invertcolor;
  usebase1:=usebase;
  pause1:=pause;
  filename1:=filename;
  pixel:=false;
  dx:=x0-width-random(100);
  dy:=y0;
  mouseoff;
  window(dx,dy,width,height,st,true);
  setcolor(darkgray);
  line(dx+border+1,dy+height-border-19-buttonheight,dx+width-border-1,dy+height-border-19-buttonheight);
  setcolor(white);
  line(dx+border+1,dy+height-border-18-buttonheight,dx+width-border-1,dy+height-border-18-buttonheight);
  x11:=dx+(width-2*buttonwidth) div 3;
  y11:=dy+height-border-10-buttonheight;
  x12:=dx+(width-2*buttonwidth) div 3+buttonwidth;
  y12:=dy+height-border-5;
  x21:=dx+2*(width-2*buttonwidth) div 3+buttonwidth;
  y21:=dy+height-border-10-buttonheight;
  x22:=dx+2*(width-2*buttonwidth) div 3+2*buttonwidth;
  y22:=dy+height-border-5;
  button(x11,y11,x12,y12,'Да',true);
  button(x21,y21,x22,y22,'Нет',true);
  for n:=1 to count do
  begin
    if (((n=3)or(n=2))and(difficulty1=3)) then setcolor(darkgray) else setcolor(black);
    settextjustify(0,1);
    x:=dx+15+textwidth(mas[1]);
    y:=dy+border+d+5+round((n-0.5)*(height-2*border-30-d-buttonheight)/count);
    outtextxy(dx+border+10,y,mas[n]);
    inbutton(x,y-round(k*textheight(mas[n])),dx+width-border-10,y+round(k*textheight(mas[n])),white);
    case n of 1:begin
                  setcolor(black);
                  settextjustify(0,1);
                  outtextxy(x+5,y+1,difficulties[difficulty1]);
                end;
              2:begin
                  setcolor(black);
                  settextjustify(0,1);
                  outtextxy(x+5,y+1,speeds[speed1]);
                end;
              3:begin
                  setcolor(black);
                  case remind1 of true:outtextxy(x+5,y+1,'выключен');
                                 false:outtextxy(x+5,y+1,'включен');
                              end;
                end;
              4:begin
                  setcolor(black);
                  settextjustify(0,1);
                  outtextxy(x+5,y+1,languages[language1]);
                end;
              5:begin
                  setcolor(black);
                  case soundeffect1 of true:outtextxy(x+5,y+1,'включен');
                                      false:outtextxy(x+5,y+1,'выключен');
                                    end;
                end;
              6:begin
                  setcolor(black);
                  str(pause1:1:10,s);
                  while s[length(s)] in ['0','.'] do delete(s,length(s),1);
                  outtextxy(x+5,y+1,s);
                end;
              7:begin
                  setcolor(black);
                  case usebase1 of true:outtextxy(x+5,y+1,'используется');
                                   false:outtextxy(x+5,y+1,'нет');
                                end;
                end;
              8:begin
                  setcolor(black);
                  case invertcolor1 of true:outtextxy(x+5,y+1,'черный');
                                       false:outtextxy(x+5,y+1,'белый');
                                     end;
                end;

           end;
  end;
  mouseon;
  repeat
    pixel:=false;
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if (l=true)and(xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15) then
    begin
      buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      windowoff(dx,dy,true);
      exit;
    end else
    if (l=true)and(xm>x11)and(ym>y11)and
       (xm<x12)and(ym<y12) then
    begin
      buttonpress(x11,y11,x12,y12,'Да');
      windowoff(dx,dy,true);
      difficulty:=difficulty1;
      speed:=speed1;
      language:=language1;
      if invertcolor1<>invertcolor then newboard:=true;
      usebase:=usebase1;
      invertcolor:=invertcolor1;
      period:=period1;
      remind:=remind1;
      soundeffect:=soundeffect1;
      pause:=pause1;
      filename:=filename1;
      exit;
    end else
    if (l=true)and(xm>x21)and(ym>y21)and
       (xm<x22)and(ym<y22) then
    begin
      buttonpress(x21,y21,x22,y22,'Нет');
      windowoff(dx,dy,true);
      exit;
    end else
    if (xm<>xm0)or(ym<>ym0)or(l=true)or(keypressed) then
    begin
      for n:=1 to count do
      begin
        x:=dx+15+textwidth(mas[1]);
        y:=dy+border+d+5+round((n-0.5)*(height-2*border-30-d-buttonheight)/count);
        if (abs(ym-y)<=round(1.5*textheight(mas[n]))) then mouseoff;
        if (abs(ym-y)<=round(0.8*textheight(mas[n])))and
           (((xm<=dx+15+textwidth(mas[n]))and(xm>=dx+border+10))or
             ((xm>=x)and(xm<=dx+width-border-10))) then
           begin
             if ((l=true)and(px<>xm)and(py<>ym))or((keypressed)and(readkey=#13)) then
             begin
               inbutton(x,y-round(k*textheight(mas[n])),dx+width-border-10,y+round(k*textheight(mas[n])),white);
               px:=xm;
               py:=ym;
               case n of 1:begin
                             str(period1-timenow,s);
                             if difficulty1=3 then difficulty1:=1 else inc(difficulty1);
                             setcolor(black);
                             outtextxy(x+5,y+1,difficulties[difficulty1]);
                             if situation>=3 then
                             if difficulty1>1 then button(530,10,getmaxx-10,40,'Отмена хода',false) else
                                                  button(530,10,getmaxx-10,40,'Отмена хода',true);
                             if difficulty1=3 then
                             begin
                               remind1:=false;
                               x:=dx+15+textwidth(mas[1]);
                               y:=dy+border+d+5+round(2.5*(height-2*border-30-d-buttonheight)/count);
                               inbutton(x,y-round(k*textheight(mas[3])),
                                        dx+width-border-10,y+round(k*textheight(mas[3])),white);
                               setcolor(black);
                               outtextxy(x+5,y+1,'включен');
                               speed1:=3;
                               settextjustify(1,1);
                               setcolor(lightgray);
                               outtextxy((520+getmaxx) div 2,(290+370) div 2,s);
                               setcolor(black);
                               outtextxy((520+getmaxx) div 2,(290+370) div 2,'5');
                               period1:=5;
                               x:=dx+15+textwidth(mas[1]);
                               y:=dy+border+d+5+round(1.5*(height-2*border-30-d-buttonheight)/count);
                               inbutton(x,y-round(k*textheight(mas[2])),
                                        dx+width-border-10,y+round(k*textheight(mas[2])),white);
                               setcolor(black);
                               settextjustify(0,1);
                               outtextxy(x+5,y+1,speeds[speed1]);
                               x:=dx+15+textwidth(mas[1]);
                               y:=dy+border+d+5+round((n-0.5)*(height-2*border-30-d-buttonheight)/count);
                             end;
                           end;
                         2:begin
                             str(period1-timenow,s);
                             if difficulty1=3 then
                             begin
                               period1:=5;
                               speed1:=3;
                             end else
                             begin
                               if speed1=3 then speed1:=1 else inc(speed1);
                               case speed1 of 1:period1:=30;
                                             2:period1:=15;
                                             3:period1:=5;
                                          end;
                             end;
                             settextjustify(1,1);
                             setcolor(lightgray);
                             outtextxy((520+getmaxx) div 2,(290+370) div 2,s);
                             setcolor(black);
                             str(period1,s);
                             outtextxy((520+getmaxx) div 2,(290+370) div 2,s);
                             settextjustify(0,1);
                             outtextxy(x+5,y+1,speeds[speed1]);
                           end;
                         3:begin
                             if difficulty1<3 then
                             begin
                               if remind1=true then remind1:=false else remind1:=true;
                             end;
                             setcolor(black);
                             case remind1 of true:outtextxy(x+5,y+1,'выключен');
                                             false:outtextxy(x+5,y+1,'включен');
                                          end;
                           end;
                         4:begin
                             if language1=1 then language1:=2 else language1:=1;
                             setcolor(black);
                             outtextxy(x+5,y+1,languages[language1]);
                           end;
                         5:begin
                             if soundeffect1=true then soundeffect1:=false else soundeffect1:=true;
                             setcolor(black);
                             case soundeffect1 of true:outtextxy(x+5,y+1,'включен');
                                                  false:outtextxy(x+5,y+1,'выключен');
                                               end;
                           end;
                         6:begin
                             setcolor(black);
                             s:='_';
                             outtextxy(x+5,y+1,s);
                             repeat
                               ch:=readkey;
                               if (ch in ['0'..'9'])or((ch='.')and(pixel=false)) then
                               begin
                                 if ch='.' then pixel:=true;
                                 setcolor(white);
                                 outtextxy(x+5,y+1,s);
                                 delete(s,length(s),1);
                                 s:=s+ch;
                                 val(s,pause1,code);
                                 s:=s+'_';
                                 setcolor(black);
                                 outtextxy(x+5,y+1,s);
                               end;
                             until (ch=#13)or(length(s)=12)or(pause1>5);
                             if (s='_')or(pause1=0) then
                             begin
                               setcolor(white);
                               outtextxy(x+5,y+1,s);
                               s:='0.75';
                               pause1:=0.75;
                             end else
                             begin
                               setcolor(white);
                               outtextxy(x+5,y+1,s);
                               delete(s,length(s),1);
                               val(s,pause1,code);
                             end;
                             if pause1>0 then while s[length(s)] in ['0','.'] do delete(s,length(s),1);
                             setcolor(black);
                             outtextxy(x+5,y+1,s);
                           end;
                         7:begin
                             if usebase1=true then usebase1:=false else usebase1:=true;
                             setcolor(black);
                             case usebase1 of true:outtextxy(x+5,y+1,'используется');
                                              false:outtextxy(x+5,y+1,'нет');
                                           end;
                           end;
                         8:begin
                             if invertcolor1=true then invertcolor1:=false else invertcolor1:=true;
                             setcolor(black);
                             case invertcolor1 of true:outtextxy(x+5,y+1,'черный');
                                                  false:outtextxy(x+5,y+1,'белый');
                                               end;
                           end;

                      end;
             end;
             setcolor(yellow);
           end else
           setcolor(black);
           if ((n=3)or(n=2))and(difficulty1=3) then setcolor(darkgray);
           outtextxy(dx+border+10,y,mas[n]);
        mouseon;
        xm0:=xm;
        ym0:=ym;
      end;
    end;
  until false;
end; {ok}
{---------------------------------------------------------------------------}
procedure information(x0,y0:word); {информация (бегущей строкой)}
const width=300;
      height=55;
      border=3;
      d=16;
      st='Информация';
      n0=21;
var x,y,n,size:integer;
    f:text;
    strings:array [1..n0] of string;
    s:string;
    p:pointer;
begin
  dx:=x0-width-random(100);
  dy:=y0;
  mouseoff;
  window(dx,dy,width,height,st,true);
  inbutton(dx+border+5,dy+border+d+5,dx+width-border-5,dy+height-border-5,black);
  mouseon;
  {$I-}
  assign(f,'help.txt');
  reset(f);
  for n:=1 to n0 do
  begin
    readln(f,s);
    strings[n]:=s;
  end;
  close(f);
  {$I+}
  n:=1;
  s:='';
  s:=strings[1];
  setviewport(dx+border+6,dy+border+d+11,dx+width-border-6,dy+height-border-11,clipon);
  settextjustify(0,1);
  x:=width-2*(border+6);
  setcolor(lightgreen);
  repeat
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if ((l=true)and(xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15)) then
    begin
      setviewport(0,0,getmaxx,getmaxy,clipoff);
      buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      windowoff(dx,dy,true);
      exit;
    end else
    if (xm<dx+border+5-9)or(ym<dy+border+d+5-16)or(xm>dx+width-border-5)or(ym>dy+height-border-5) then
      begin
        x:=x-1;
        if (x mod textwidth(' ')=0)and(x<1) then
        begin
          delete(s,1,1);
          x:=x+textwidth(' ');
        end;
        if length(s)<width div textwidth(' ') then
        begin
          inc(n);
          if n=n0+1 then n:=1;
          s:=s+' '+strings[n];
        end;
        vertwait;
        clearviewport;
        outtextxy(x,5,s);
      end;
  until false;
end; {ok}
{---------------------------------------------------------------------------}
procedure Authorship(x0,y0:word); {справка об авторе}
const width=240;
      height=85;
      d=16;
      st1='Дугин Андрей Владимирович,';
      st2='г.Воркута республики Коми,';
      st3='улица Авиационная, 55-4,';
      st4='телефон (82151) 4-15-15';
      count=4;
      mas:array [1..count] of string=(st1,st2,st3,st4);
      st='Сведения об авторе';
      border=3;
      k=0.6;
var p:pointer;
    x,y,size,n,xm0,ym0,px,py,i,code:integer;
    s:string;
    ch:char;
    pixel:boolean;
begin
  dx:=x0;
  dy:=y0+10+random(20);
  mouseoff;
  window(dx,dy,width,height,st,true);
  inbutton(dx+border+5,dy+border+d+5,dx+width-border-5,dy+height-border-5,white);
  settextjustify(1,1);
  for n:=1 to count do
  begin
    setcolor(black);
    x:=dx+width div 2;
    y:=dy+border+d+5+round((n-0.5)*(height-2*border-10-d)/count)+1;
    outtextxy(x,y,mas[n]);
  end;
  mouseon;
  repeat
    {getmousexyondown(xm,ym,0,n1,l,r,m)}
    if commander=false then getmouseinfo(xm,ym,l,r,m);
  until ((l=true)and(xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15))or
         ((keypressed)and(readkey in [#27,#107]));
  buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
  windowoff(dx,dy,true);
  xm0:=xm;
  ym0:=ym;
  exit;
end; {ok}
{---------------------------------------------------------------------------}
function FileWindow(st:string;x,y:word):boolean; {окно смены файла}
const width=165;
      height=74;
      border=3;
      buttonheight=14;
      buttonwidth=55;
      d=16;
var dx,dy,size,x11,y11,x12,y12,x21,y21,x22,y22,n:integer;
    p:pointer;
    lastcolor:word;
    s,filename1:string;
    ch:char;
    permission,exist,yesbutton:boolean;
    f:text;
begin
  filewindow:=false;
  permission:=false;
  filename1:=filename;
  lastcolor:=black;
  randomize;
  dx:=x-width-random(50);
  dy:=y;
  mouseoff;
  window(dx,dy,width,height,st,true);
  inbutton(dx+border+5+textwidth('Файл:'),dy+d+border+9-round(0.6*textheight(' ')),
           dx+width-border-5,dy+d+border+9+round(0.6*textheight(' ')),white);
  setcolor(black);
  outtextxy(dx+border+5,dy+d+border+10,'Файл:');
  outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,filename);
  x11:=dx+(width-2*buttonwidth) div 3;
  y11:=dy+height-border-10-buttonheight;
  x12:=dx+(width-2*buttonwidth) div 3+buttonwidth;
  y12:=dy+height-border-5;
  x21:=dx+2*(width-2*buttonwidth) div 3+buttonwidth;
  y21:=dy+height-border-10-buttonheight;
  x22:=dx+2*(width-2*buttonwidth) div 3+2*buttonwidth;
  y22:=dy+height-border-5;
  button(x11,y11,x12,y12,'Да',true);
  button(x21,y21,x22,y22,'Нет',true);
  setcolor(darkgray);
  line(dx+border+1,y11-7,dx+width-border-1,y11-7);
  setcolor(white);
  line(dx+border+1,y11-6,dx+width-border-1,y11-6);
  mouseon;
  exist:=true;
  yesbutton:=true;
  repeat
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if (xm>dx+border+5)and(ym>dy+d+border+10-round(0.6*textheight(' ')))and
       (xm<dx+width-border-5)and(ym<dy+d+border+9+round(0.6*textheight(' '))) then
      begin
        if lastcolor=black then
        begin
          lastcolor:=yellow;
          setcolor(yellow);
          if (xm<dx+border+5+textwidth('Файл:')) then mouseoff;
          outtextxy(dx+border+5,dy+d+border+10,'Файл:');
          if (xm<dx+border+5+textwidth('Файл:')) then mouseon;
        end;
        if (l=true)or((keypressed)and(readkey=#13)) then
        begin
          mouseoff;
          setcolor(white);
          outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,filename1);
          setcolor(black);
          s:='_.sav';
          outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
          repeat
            ch:=readkey;
            if (ch in ['A'..'Z','a'..'z','А'..'Я','а'..'я','0'..'9']) then
              begin
                setcolor(white);
                outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
                delete(s,length(s)-4,5);
                s:=s+ch+'_.sav';
                setcolor(black);
                outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
              end else
            if (ch=#8)and(length(s)>5) then
              begin
                setcolor(white);
                outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
                delete(s,length(s)-5,1);
                setcolor(black);
                outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
              end;
          until (ch=#13)or(length(s)=13);
          if s='_.sav' then
            begin
              setcolor(white);
              outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
              s:=filename;
              filename1:=filename;
            end else
            begin
              setcolor(white);
              outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
              delete(s,length(s)-4,5);
              s:=s+'.sav';
              filename1:=s;
            end;
          setcolor(black);
          outtextxy(dx+border+10+textwidth('Файл:'),dy+d+border+10,s);
          mouseon;
        end;
      end else
    if lastcolor=yellow then
      begin
        lastcolor:=black;
        setcolor(black);
        if (xm<dx+border+5+textwidth('Файл:')) then mouseoff;
        outtextxy(dx+border+5,dy+d+border+10,'Файл:');
        if (xm<dx+border+5+textwidth('Файл:')) then mouseon;
      end;
    if fileexist(filename1,false)=false then
    begin
      if (st<>'Сохранить файл') then
        begin
          exist:=false;
          if yesbutton=true then button(x11,y11,x12,y12,'Да',false);
          yesbutton:=false;
        end else
        begin
          exist:=true;
          if yesbutton=false then button(x11,y11,x12,y12,'Да',true);
          yesbutton:=true;
        end;
    end;
    if l=true then
    begin
      if (xm>x11)and(ym>y11)and(xm<x12)and(ym<y12)and(exist=true) then
      begin
        filewindow:=true;
        permission:=true;
        filename:=filename1;
        buttonpress(x11,y11,x12,y12,'Да');
      end else
      if (xm>x21)and(ym>y21)and(xm<x22)and(ym<y22) then
      begin
        permission:=true;
        buttonpress(x21,y21,x22,y22,'Нет');
      end else
      if (xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15) then
      begin
        permission:=true;
        buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      end;
    end;
  until permission=true;
  windowoff(dx,dy,true);
end; {ok}
{---------------------------------------------------------------------------}
procedure Save; {сохранение игры}
var f,c:text;
begin
  if commander=false then getmouseinfo(xm,ym,l,r,m);
  if filewindow('Сохранить файл',xm,ym)=false then exit;
  {$I-}
  assign(f,filename);
  rewrite(f);
  {$I-}
  writeln(f,difficulty);
  writeln(f,speed);
  writeln(f,remind);
  writeln(f,language);
  writeln(f,soundeffect);
  writeln(f,pause:1:3);
  assign(c,'autosave.sav');
  reset(c);
  while not eof(c) do
  begin
    readln(c,st);
    writeln(f,st);
  end;
  close(c);
  writeln(f,'');
  assign(c,'movie.sav');
  reset(c);
  while not eof(c) do
  begin
    readln(c,st);
    writeln(f,st);
  end;
  close(f);
  close(c);
end; {ok}
{---------------------------------------------------------------------------}
procedure AutoSave; {автосохранение для возможности возврата хода}
var f:text;
begin
  assign(f,'autosave.sav');
  {$I-}
  reset(f);
  {$I+}
  if ioresult<>0 then
  begin
    situation:=0;
    rewrite(f);
    writeln(f,'bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww');
  end;
  append(f);
  for y:=1 to y0 do
  for x:=1 to x0 do
  if (x mod 2<>y mod 2) then
  begin
    if (x=x0-1)and(y=y0) then
      writeln(f,field[y,x]) else
      write(f,field[y,x]);
  end;
  close(f);
end; {ok}
{---------------------------------------------------------------------------}
procedure movie; {сохранение позиций для возможного просмотра}
var f:text;
    x,y:byte;
begin
  assign(f,'movie.sav');
  {$I-}
  reset(f);
  if ioresult<>0 then
  begin
    rewrite(f);
    writeln(f,'bbbbbbbbbbbbnnnnnnnnwwwwwwwwwwww');
  end;
  {$I+}
  append(f);
  for y:=1 to y0 do
  for x:=1 to x0 do
  if x mod 2<>y mod 2 then
  begin
    if (x=x0-1)and(y=y0) then writeln(f,field[y,x]) else
                              write(f,field[y,x]);
  end;
  close(f);
end; {ok}
{---------------------------------------------------------------------------}
procedure WriteAction(x1,y1,x2,y2:byte;color:word); {действие в координатах}
const d=0;
      delta=2;
      limit=44;
var p:pointer;
    size:integer;
begin
  movie;
  settextjustify(centertext,centertext);
  case color of white:begin
                        if (stroka>=limit)and(lastcolor=color) then
                        begin
                          size:=imagesize(394,(stroka0+delta)*textheight(' ')+d,521,374);
                          getmem(p,size);
                          mouseoff;
                          getimage(394,(stroka0+delta)*textheight(' ')+d,521,374,p^);
                          inbutton(394,60,456,375,black);
                          inbutton(460,60,521,375,black);
                          putimage(394,stroka0*textheight(' '),p^,normalput);
                          mouseon;
                          freemem(p,size);
                        end;
                        if (lastcolor=color)and(stroka<limit) then stroka:=stroka+delta;
                        if invertcolor=false then setcolor(white) else setcolor(lightgray);
                        outtextxy((394+456) div 2,stroka*textheight(' '),abc[x1]+digits[y1]+'-'+abc[x2]+digits[y2]);
                        if invertcolor=true then
                        if stroka<limit then stroka:=stroka+delta;
                      end;
                black:begin
                        if stroka>=limit then
                        begin
                          size:=imagesize(394,(stroka0+delta)*textheight(' ')+d,521,374);
                          getmem(p,size);
                          mouseoff;
                          getimage(394,(stroka0+delta)*textheight(' ')+d,521,374,p^);
                          inbutton(394,60,456,375,black);
                          inbutton(460,60,521,375,black);
                          putimage(394,stroka0*textheight(' '),p^,normalput);
                          mouseon;
                          freemem(p,size);
                        end;
                        if invertcolor=false then setcolor(lightgray) else setcolor(white);
                        outtextxy((460+521) div 2,stroka*textheight(' '),abc[x1]+digits[y1]+'-'+abc[x2]+digits[y2]);
                        if invertcolor=false then
                        if stroka<limit then stroka:=stroka+delta;
                      end;
             end;
  lastcolor:=color;
end; {ok}
{---------------------------------------------------------------------------}
procedure Effect;
begin
  if soundeffect=true then
  begin
    sound(500);
    delay(1000);
    nosound;
  end;
  delay(200);
end; {ok}
{---------------------------------------------------------------------------}
procedure Away(x,y:byte); {удаление шашки с экрана и с доски}
var l:longint;
    r:byte;
    x1,y1,xx,yy:integer;
begin
  r:=(width-4-border) div 2+1;
  mouseoff;
  if field[y,x] in ['W','B'] then
  begin
    randomize;
    l:=0;
    repeat
      xx:=x*width+width div 2;
      yy:=y*width+width div 2;
      x1:=xx+random(2*r+1)-r;
      y1:=yy+random(2*r+1)-r;
      if sqrt(sqr(x1-xx)+sqr(y1-yy))<=r then
      if getpixel(x1,y1)<>brown then
      begin
        putpixel(x1,y1,brown);
        delay(round(1*pause));
        inc(l);
      end;
    until l=round(pi*sqr(r-1));
  end else
  if ((field[y,x]='w')and(invertcolor=false))or
     ((field[y,x]='b')and(invertcolor=true)) then
  begin
    dec(r);
    setlinestyle(solidln,0,3);
    setcolor(yellow);
    rectangle(width div 2,width div 2+1,(x0+1)*width+width div 2,(y0+1)*width+width div 2);
    setlinestyle(solidln,0,1);
    setcolor(magenta);
    setrgbpalette(magenta,63,63,63);
    setfillstyle(solidfill,magenta);
    vertwait;
    sector(x*width+width div 2,y*width+width div 2,0,360,r,r);
    setcolor(red);
    setrgbpalette(red,21,21,21);
    circle(x*width+width div 2,y*width+width div 2,r);
    circle(x*width+width div 2,y*width+width div 2,r-4);
    circle(x*width+width div 2,y*width+width div 2,r-8);
    mouseon;
    for r:=63 downto 42 do
    begin
      setrgbpalette(magenta,r,63-2*(63-r),63-(63-r)*3);
      setrgbpalette(red,21+(63-r),21,63-r);
      delay(round(10*pause));
    end;
    mouseoff;
    square(x,y,brown);
    mouseon;
    setlinestyle(solidln,0,3);
    setrgbpalette(red,63,63,22);
    setcolor(red);
    mouseoff;
    rectangle(width div 2,width div 2+1,(x0+1)*width+width div 2,(y0+1)*width+width div 2);
  end else
  if ((field[y,x]='b')and(invertcolor=false))or
     ((field[y,x]='w')and(invertcolor=true)) then
  begin
    dec(r);
    setlinestyle(solidln,0,3);
    setcolor(yellow);
    rectangle(width div 2,width div 2+1,(x0+1)*width+width div 2,(y0+1)*width+width div 2);
    setlinestyle(solidln,0,1);
    setcolor(magenta);              {magenta=black,red=lightgray);}
    setrgbpalette(magenta,0,0,0);
    setfillstyle(solidfill,magenta);
    vertwait;
    sector(x*width+width div 2,y*width+width div 2,0,360,r,r);
    setcolor(red);
    setrgbpalette(red,42,42,42);
    circle(x*width+width div 2,y*width+width div 2,r);
    circle(x*width+width div 2,y*width+width div 2,r-4);
    circle(x*width+width div 2,y*width+width div 2,r-8);
    mouseon;
    for r:=0 to 42 do
    begin   {brown=(42,21,0),black=(0,0,0),lightgray=(42,42,42)}
      setrgbpalette(magenta,r,r div 2,0);
      setrgbpalette(red,42,42-r div 2,42-r);
      delay(round(10*pause));
    end;
    mouseoff;
    square(x,y,brown);
    mouseon;
    setlinestyle(solidln,0,3);
    setrgbpalette(red,63,63,22);
    setcolor(red);
    mouseoff;
    rectangle(width div 2,width div 2+1,(x0+1)*width+width div 2,(y0+1)*width+width div 2);
  end;
  square(x,y,brown);
  field[y,x]:='n';
  mouseon;
end; {ok}
{---------------------------------------------------------------------------}
procedure DraughtBeat(color:word); {изображение сбитой шашки}
begin
  if color=white then inc(beat_w) else
  if color=black then
  begin
    inc(beat_b);
    mustbeat:=false;
  end;
  if color=white then draughtsman(beat_w*width+width div 2-7,(y0+2)*width+12+1,false,getcolor(white));
  if color=black then draughtsman(beat_b*width+width div 2-7,(y0+3)*width+11-1,false,getcolor(black));
end; {ok}
{---------------------------------------------------------------------------}
procedure BackSpace; {отмена хода}
var st:string;
    f,c:text;
    n,x,y:integer;
begin
  inbutton(394,60,456,375,black);
  inbutton(460,60,521,375,black);
  inbutton(width-13,395,520,getmaxy-10,cyan);
  w:=0;
  b:=0;
  beat_w:=0;
  beat_b:=0;
  stroka:=stroka0;
  assign(f,'autosave.sav');
  reset(f);
  assign(c,'copy.sav');
  rewrite(c);
  dec(situation);
  if situation=0 then
  begin
    button(530,70,getmaxx-10,100,'Сохранить',false);
    button(530,10,getmaxx-10,40,'Отмена хода',false);
  end;
  for n:=1 to situation+1 do
  begin
    readln(f,st);
    writeln(c,st);
  end;
  close(f);
  close(c);
  erase(f);
  rename(c,'autosave.sav');
  for y:=1 to y0 do
  for x:=1 to x0 do
  if x mod 2<>y mod 2 then
  begin
    if (st[1]='n')and(field[y,x]<>'n') then square(x,y,brown);
    case st[1] of 'w':begin
                        draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(white));
                        inc(w);
                      end;
                  'W':begin
                        draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(white));
                        inc(w);
                      end;
                  'b':begin
                        draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
                        inc(b);
                      end;
                  'B':begin
                        draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(black));
                        inc(b);
                      end;
               end;
    field[y,x]:=st[1];
    delete(st,1,1);
  end;
  if w<12 then while beat_w<(12-w) do draughtbeat(white);
  if b<12 then while beat_b<(12-b) do draughtbeat(black);
  setlinestyle(solidln,0,1);
end; {ok}
{---------------------------------------------------------------------------}
procedure date; {вывод даты}
var year,month,day,DayOfWeek:word;
    s,st:string;
begin
  getdate(year,month,day,dayofweek);
  str(day,s);
  st:=s+'.';
  str(month,s);
  if month in [1..9] then
    st:=st+'0'+s+'.' else st:=st+s+'.';
  str(year,s);
  st:=st+s;
  settextjustify(centertext,centertext);
  setcolor(black);
  outtextxy((520+getmaxx) div 2,(437+469) div 2,st);
end; {ok}
{---------------------------------------------------------------------------}
procedure ShowTime; {текущее время}
var hour,minute,second,sec:word;
    st,s:string;
begin
  st:='';
  gettime(hour,minute,second,sec);
  str(hour,s);
  if hour in [0..9] then
    st:=st+'0'+s+':' else st:=st+s+':';
  str(minute,s);
  if minute in [0..9] then
    st:=st+'0'+s else st:=st+s;
  if st<>timestring then
  begin
    setcolor(lightgray);
    settextjustify(centertext,centertext);
    outtextxy((520+getmaxx) div 2,(395+427) div 2,TimeString);
    setcolor(black);
    outtextxy((520+getmaxx) div 2,(395+427) div 2,st);
  end;
  timestring:=st
end; {ok}
{---------------------------------------------------------------------------}
procedure Board(special:boolean); {подготовка к игре}
var x,y:integer;
label here;
begin
  if special=true then goto here;
  button(385,1,getmaxx,383,'',true);
  button(width-23,385,getmaxx,getmaxy,'',true);
  button(530,10,getmaxx-10,40,'Отмена хода',false);
  button(530,40,getmaxx-10,70,'Открыть',true);
  button(530,70,getmaxx-10,100,'Сохранить',false);
  button(530,100,getmaxx-10,130,'Информация',true);
  button(530,130,getmaxx-10,160,'Опции',true);
  button(530,160,getmaxx-10,190,'Просмотр',true);
  button(530,190,getmaxx-10,220,'Развитие',true);
  button(530,220,getmaxx-10,250,'Новая игра',true);
  button(530,250,getmaxx-10,280,'Выход',true);
  button(17,1,382,20,'Автор и разработчик программы: Дугин Андрей',true);
  inbutton(395,10,455,55,lightgray);
  inbutton(460,10,520,55,lightgray);
  draughtsman(425,33,false,getcolor(white));
  draughtsman(490,33,false,getcolor(black));
  inbutton(530,395,getmaxx-10,427,lightgray);
  inbutton(530,437,getmaxx-10,469,lightgray);
  date;
  showtime;
  inbutton(530,290,getmaxx-10,370,lightgray);
  setcolor(black);
  settextjustify(1,1);
  x:=(520+getmaxx) div 2;
  y:=(290+370) div 2;
  outtextxy(x,y-20,'Осталось');
  outtextxy(x,y,'30');
  timeleft:='30';
  outtextxy(x,y+20,'секунд');
  setlinestyle(solidln,0,3);
  setrgbpalette(red,63,63,22);
  setcolor(red);
  rectangle(width div 2,width div 2+1,(x0+1)*width+width div 2,(y0+1)*width+width div 2);
  setlinestyle(solidln,0,1);
  setrgbpalette(green,25,0,15);
  setfillstyle(solidfill,green);
  bar(width div 2+3,width div 2+4,(x0+1)*width+width div 2-3,(y0+1)*width+width div 2-3);
  here:
  setrgbpalette(cyan,0,15,0);
  inbutton(width-13,395,520,getmaxy-10,cyan);
  inbutton(394,60,456,375,black);
  inbutton(460,60,521,375,black);
  vertwait;
  settextjustify(0,2);
  if special=false then
  for y:=1 to y0 do
  for x:=1 to x0 do
  begin
    if x mod 2=y mod 2 then square(x,y,yellow) else
    square(x,y,brown);
    if (x mod 2<>y mod 2)and(y>y0-3) then
    begin
      field[y,x]:='w';
      draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(white))
    end else
    if (x mod 2<>y mod 2)and(y<=3) then
    begin
      field[y,x]:='b';
      draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
    end else
    field[y,x]:='n';
    setcolor(yellow);
    if x=1 then
    begin
      outtextxy(3*width div 4-2,y*width+width div 2,digits[y]);
      outtextxy((x0+1)*width+6,y*width+width div 2,digits[y]);
    end;
    if y=y0 then
    begin
      outtextxy(x*width+width div 2,3*width div 4-2,abc[x]);
      outtextxy(x*width+width div 2,(y+1)*width+width div 8,abc[x]);
    end;
  end else
  if special=true then
  for y:=1 to y0 do
  for x:=1 to x0 do
    if (x mod 2<>y mod 2) then
    begin
      if (y<4)and(field[y,x]<>'b') then
      begin
        field[y,x]:='b';
        draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
      end else
      if (y in [4..y0-3])and(field[y,x]<>'n') then
      begin
        field[y,x]:='n';
        square(x,y,brown);
      end else
      if (y in [y0-2..y0])and(field[y,x]<>'w') then
      begin
        field[y,x]:='w';
        draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(white));
      end;
    end
end; {ok}
{---------------------------------------------------------------------------}
procedure Load(ok:boolean); {загрузка игры из файла}
var st:string;
    x,y,n:integer;
    code:integer;
    f,c:text;
begin
  if commander=false then getmouseinfo(xm,ym,l,r,m);
  if ok=true then
  if filewindow('Загрузить файл',xm,ym)=false then exit;
  button(530,70,getmaxx-10,100,'Сохранить',true);
  inbutton(394,60,456,375,black);
  inbutton(460,60,521,375,black);
  inbutton(width-13,395,520,getmaxy-10,cyan);
  stroka:=stroka0;
  {$I-}
  assign(f,filename);
  reset(f);
  if ioresult=0 then
  begin
    readln(f,st);
    val(st,difficulty,code);
    readln(f,st);
    val(st,speed,code);
    case speed of 1:period:=30;
                  2:period:=15;
                  3:period:=5;
               end;
    readln(f,st);
    if st='TRUE' then remind:=true else remind:=false;
    readln(f,st);
    val(st,language,code);
    readln(f,st);
    if st='TRUE' then soundeffect:=true else soundeffect:=false;
    readln(f,st);
    val(st,pause,code);
    situation:=0;
    w:=0;
    b:=0;
    beat_w:=0;
    beat_b:=0;
    assign(c,'autosave.sav');
    rewrite(c);
    situation:=0;
    st:='0';
    while st<>'' do
    begin
      readln(f,st);
      if st<>'' then
      begin
        inc(situation);
        writeln(c,st);
      end;
    end;
    close(c);
    close(f);
    reset(f);
    for n:=1 to situation+6 do
    readln(f,st);
    for y:=1 to y0 do
    for x:=1 to x0 do
    if x mod 2<>y mod 2 then
    begin
      if (st[1]='n')and(field[y,x]<>'n') then square(x,y,brown);
      case st[1] of 'w':begin
                          draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(white));
                          inc(w);
                        end;
                    'W':begin
                          draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(white));
                          inc(w);
                        end;
                    'b':begin
                          draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
                          inc(b);
                        end;
                    'B':begin
                          draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(black));
                          inc(b);
                        end;
                 end;
      field[y,x]:=st[1];
      delete(st,1,1);
    end;
    if w<12 then while beat_w<(12-w) do draughtbeat(white);
    if b<12 then while beat_b<(12-b) do draughtbeat(black);
    readln(f,st);
    assign(c,'movie.sav');
    rewrite(c);
    while not eof(f) do
    begin
      readln(f,st);
      writeln(c,st);
    end;
    close(c);
    close(f);
    setlinestyle(solidln,0,1);
  end;
  if (situation>=3)and(difficulty=1) then button(530,10,getmaxx-10,40,'Отмена хода',true) else
                                          button(530,10,getmaxx-10,40,'Отмена хода',false);
end; {ok}
{---------------------------------------------------------------------------}
procedure play; {просмотр последовательности действий в файле}
var f:text;
    lst:string;
    x,y:integer;
    first:boolean;
label lb;
begin
  if commander=false then getmouseinfo(xm,ym,l,r,m);
  if filewindow('Просмотр файла',xm,ym)=false then exit;
  first:=false;
  st:='0';
  assign(f,filename);
  reset(f);
  inbutton(394,60,456,375,black);
  inbutton(460,60,521,375,black);
  inbutton(width-13,395,520,getmaxy-10,cyan);
  while st<>'' do readln(f,st);
  while not eof(f) do
  begin
    readln(f,st);
    for y:=1 to y0 do
    for x:=1 to x0 do
    if x mod 2<>y mod 2 then
    begin
      if (st[1]='n')and(field[y,x]<>'n') then square(x,y,brown);
      if (st[1]<>field[y,x]) then
      case st[1] of 'w':draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(white));
                    'W':draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(white));
                    'b':draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
                    'B':draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(black));
                 end;
      field[y,x]:=st[1];
      delete(st,1,1);
    end;
    if keypressed then goto lb;
    if (first=true)and(soundeffect=true) then effect;
    delay(round(3000*pause));
    first:=true;
  end;
  lb:load(false);
  close(f);
  gettime(hour,minute,second,sec100);
end; {ok}
{---------------------------------------------------------------------------}
procedure cancel; {отмена выделений}
var x,y:byte;
begin
  setcolor(black);
  for y:=1 to y0 do
  for x:=1 to x0 do
  begin
    mouseoff;
    rectangle(x*width,y*width,(x+1)*width,(y+1)*width);
    mouseon;
  end;
end; {ok}
{---------------------------------------------------------------------------}
procedure BeatWindow; {сообщение об истечении времени и сбитой шашке}
const width=250;
      height=65;
      border=3;
      buttonheight=14;
      buttonwidth=55;
      d=16;
      st1='Вашу шашку СОЖРАЛИ,';
      st2='потому что Вы долго думали.';
var dx,dy,size:integer;
    p:pointer;
    lastcolor:word;
    permission:boolean;
    n:integer;
begin
  permission:=false;
  randomize;
  dx:=(getmaxx-width) div 2;
  dy:=(getmaxy-height) div 2;;
  mouseoff;
  window(dx,dy,width,height,'Внимание!',true);
  settextjustify(1,1);
  setcolor(black);
  outtextxy(dx+width div 2,dy+d+border+(height-2*border-d) div 3,st1);
  outtextxy(dx+width div 2,dy+d+border+2*(height-2*border-d) div 3,st2);
  mouseon;
  repeat
    if commander=false then getmouseinfo(xm,ym,l,r,m);
    if (l=true)and(xm>dx+width-border-15)and(ym>dy+border+2)and(xm<dx+width-border-1)and(ym<dy+border+15) then
      begin
        permission:=true;
        buttonpress(dx+width-border-15,dy+border+2,dx+width-border-1,dy+border+15,'X');
      end;
  until permission=true;
  windowoff(dx,dy,true);
end; {ok}
{---------------------------------------------------------------------------}
procedure confiscate(special:boolean); {изъятие шашки}
var x,y,d,n:byte;
begin
  for y:=1 to y0 do
  for x:=1 to x0 do
  if field[y,x] in whites then
  begin
    setlinestyle(solidln,0,3);
    for n:=1 to 5 do
    begin
      setcolor(white);
      mouseoff;
      rectangle(x*width,y*width,(x+1)*width,(y+1)*width);
      mouseon;
      if soundeffect=true then sound(1000);
      delay(round(500*pause));
      setcolor(black);
      mouseoff;
      rectangle(x*width,y*width,(x+1)*width,(y+1)*width);
      mouseon;
      nosound;
      delay(round(500*pause));
    end;
    field[y,x]:='n';
    square(x,y,brown);
    draughtbeat(white);
    setlinestyle(solidln,0,1);
    exit;
  end;
  if special=true then beatwindow;
end; {ok}
{---------------------------------------------------------------------------}
procedure TVSetOff; {"выключение" экрана}
var s:integer;
begin
  mouseoff;
  setcolor(red);
  setrgbpalette(red,63,63,63);
  setfillstyle(solidfill,red);
  x:=getmaxx;
  y:=getmaxy;
  for s:=y div 2 downto 0 do
  begin
    bar(1,s-1,x,s);
    bar(1,y-s-1,x,y-s);
  end;
  setfillstyle(solidfill,black);
  for s:=0 to y div 2-2 do
  begin
    bar(1,s-1,x,s);
    bar(1,y-s-1,x,y-s);
    delay(round(3*pause));
  end;
  setfillstyle(solidfill,black);
  for s:=1 to x div 2-1 do
  begin
    bar(1,y div 2-2,s,y div 2+2);
    bar(x-s,y div 2-2,x,y div 2+2);
    delay(round(pause));
  end;
  for s:=63 downto 0 do
  begin
    setrgbpalette(red,s,s,s);
    delay(round(pause));
  end;
end; {ok}
{---------------------------------------------------------------------------}
procedure Quit; {выход из игры}
var f,c:text;
begin
  if filename<>'' then
  begin
    assign(f,'draughts.his');
    rewrite(f);
    writeln(f,filename);
    writeln(f,pause);
    close(f);
  end;
  delay(round(1000*pause));
  tvsetoff;
  if shirm<>nil then freemem(shirm,imagesize(0,0,x0*width,y0*width));
  closegraph;
  eraseall;
  halt(0);
end; {ok}
{---------------------------------------------------------------------------}
function commander:boolean;
const step=5;
var ch:char;
    n:byte;
begin
  {l:=false;
  r:=false;
  commander:=false;
  if keypressed then ch:=readkey;
  if ord(ch)in [13,27,32,72,75,77,80,71,73,79,81] then
  begin
    commander:=true;
    getmouseinfo(xm,ym,l,r,m);
    case ch of #27:quit;
               #71:for n:=1 to 100 do
                   begin
                     vertwait;
                     setmousexy(xm-n,ym);
                   end;
               #79:for n:=1 to 100 do
                   begin
                     vertwait;
                     setmousexy(xm+n,ym);
                   end;
               #73:for n:=1 to 100 do
                   begin
                     vertwait;
                     setmousexy(xm,ym-n);
                   end;
               #81:for n:=1 to 100 do
                   begin
                     vertwait;
                     setmousexy(xm,ym+n);
                   end;

               #72:for n:=1 to step do
                   begin
                     vertwait;
                     setmousexy(xm,ym-n);
                   end;
               #80:for n:=1 to step do
                   begin
                     vertwait;
                     setmousexy(xm,ym+n);
                   end;
               #75:for n:=1 to step do
                   begin
                     vertwait;
                     setmousexy(xm-n,ym);
                   end;
               #77:for n:=1 to step do
                   begin
                     vertwait;
                     setmousexy(xm+n,ym);
                   end;
               #13:l:=true;
               #32:r:=true;
            end;
  end;}
  commander:=false;
end; {ok}
{---------------------------------------------------------------------------}
function Wait(var hour,minute,second:word):boolean; {счетчик времени}
var h,min,s,s100:word;
    b,w,x,y:byte;
begin
  settextjustify(1,1);
  wait:=false;
  if startgame=true then
  begin
    repeat
      gettime(h,min,s,s100);
      if timenow<>(h-hour)*3600+(min-minute)*60+(s-second) then
      begin
        timenow:=(h-hour)*3600+(min-minute)*60+(s-second);
        if timenow<=period then
        begin
          setcolor(lightgray);
          vertwait;
          mouseoff;
          outtextxy((520+getmaxx) div 2,(290+370) div 2,timeleft);
          mouseon;
          str(period-timenow,timeleft);
          setcolor(black);
          mouseoff;
          outtextxy((520+getmaxx) div 2,(290+370) div 2,timeleft);
          mouseon;
        end;
      end;
      if commander=false then getmouseinfo(xm,ym,l,r,m);
    until (l=true)or(r=true)or(timenow=period);
    if (l=true)or(r=true) then exit;
    if timenow>=period then
    begin
      cancel;
      confiscate(true);
      wait:=true;
    end;
    w:=0;
    for y:=1 to y0 do
    for x:=1 to x0 do
      if field[y,x] in whites then inc(w);
    if w=0 then
    if onceagain(0)=false then quit;
  end;
  if timenow>=period then beatwindow;
end; {ok}
{---------------------------------------------------------------------------}
function DangerousPosition(x,y:byte;mas:chessboard;color:word):boolean;
         {проверка опасной позиции}
var r,d:byte;
    close:array [1..4] of boolean;
begin
  for d:=1 to 4 do close[d]:=false;
  dangerousposition:=false;
  for r:=1 to maximum(x,y) do
  for d:=1 to 4 do
    if between(x-dir[d,1],y-dir[d,2]) then
    if between(x+r*dir[d,1],y+r*dir[d,2]) then
    if (mas[y-dir[d,2],x-dir[d,1]]='n') then
        begin
          if r=1 then
          begin
             if (((color=black)and(mas[y+dir[d,2],x+dir[d,1]] in whites))or
                 ((color=white)and(mas[y+dir[d,2],x+dir[d,1]] in blacks))) then
               begin
                 dangerousposition:=true;
                 exit;
               end else
             if ((color=black)and(mas[y+dir[d,2],x+dir[d,1]] in blacks))or
                ((color=white)and(mas[y+dir[d,2],x+dir[d,1]] in whites)) then
                close[d]:=true;
          end else
          if r>1 then
            begin
              if ((color=black)and(mas[y+r*dir[d,2],x+r*dir[d,1]] in ['b','B','w']))or
                 ((color=white)and(mas[y+r*dir[d,2],x+r*dir[d,1]] in ['w','W','b'])) then
                 close[d]:=true;
              if (close[d]=false) then
              if (((color=black)and(mas[y+r*dir[d,2],x+r*dir[d,1]]='W'))or
                  ((color=white)and(mas[y+r*dir[d,2],x+r*dir[d,1]]='B')))then
                begin
                  dangerousposition:=true;
                  exit;
                end;
            end;
        end;
end; {ok}
{---------------------------------------------------------------------------}
function DangerousBeat(x1,y1,x2,y2,bx,by:byte;mas:chessboard;color:word):boolean;
var r,d:byte;
    close:array [1..4] of boolean;
begin
  for d:=1 to 4 do close[d]:=false;
  dangerousbeat:=false;
  for r:=1 to maximum(x2,y2) do
  for d:=1 to 4 do
    if between(x2+r*dir[d,1],y2+r*dir[d,2]) then
    if between(x2-r*dir[d,1],y2-r*dir[d,2]) then
        begin
          if (r=1)and
             (((color=black)and(mas[y2+dir[d,2],x2+dir[d,1]] in whites))or
              ((color=white)and(mas[y2+dir[d,2],x2+dir[d,1]] in blacks)))and
             ((mas[y2-dir[d,2],x2-dir[d,1]]='n')or
              ((x2-dir[d,1]=bx)and(y2-dir[d,2]=by))) then
            begin
              dangerousbeat:=true;
              exit;
            end else
          if (r>1) then
            begin
              if (((color=black)and(mas[y2+r*dir[d,2],x2+r*dir[d,1]]<>'W'))or
                  ((color=white)and(mas[y2+r*dir[d,2],x2+r*dir[d,1]]<>'B')))and
                 (mas[y2+r*dir[d,2],x2+r*dir[d,1]]<>'n')and
                 ((x2+r*dir[d,1]<>bx)or(y2+r*dir[d,2]<>by)) then
                 close[d]:=true else
              if (close[d]=false)and
                 (((color=black)and(mas[y2+r*dir[d,2],x2+r*dir[d,1]]='W'))or
                  ((color=white)and(mas[y2+r*dir[d,2],x2+r*dir[d,1]]='B')))and
                 ((mas[y2-dir[d,2],x2-dir[d,1]]='n')or
                  ((x2-dir[d,1]=bx)and(y2-dir[d,2]=by)))then
                begin
                  dangerousbeat:=true;
                  exit;
                end;
            end;
        end;
end;
{---------------------------------------------------------------------------}
function DamkaOnLine(x,y,d:byte):boolean; {присутствие вражеской дамки}
var x1,y1:byte;
begin
  x1:=x;
  y1:=y;
  damkaonline:=false;
  repeat
    x1:=x1+dir[d,1];
    y1:=y1+dir[d,2];
    if between(x1,y1) then
      begin
        if (field[y1,x1]<>'n')and(field[y1,x1]<>'W')then
          begin
            damkaonline:=false;
            exit;
          end else
        if (field[y1,x1]='W') then
          begin
            damkaonline:=true;
            exit;
          end;
      end;
  until between(x1,y1)=false;
end;
{---------------------------------------------------------------------------}
function freeway(x1,y1,x2,y2:byte;mas:chessboard):boolean;
                {путь между точками свободен}
var ok:boolean;
    n,x,y:byte;
begin
  freeway:=true;
  x:=x1;
  y:=y1;
  repeat
    x:=x+abs(x2-x1) div (x2-x1);
    y:=y+abs(y2-y1) div (y2-y1);
    if mas[y,x]<>'n' then
    begin
      freeway:=false;
      exit;
    end;
  until (abs(x-x2)=1)and(abs(y-y2)=1);
end;
{---------------------------------------------------------------------------}
function exist(x1,y1,x2,y2:byte;var bx,by:byte;color:word;mas:chessboard):byte;
         {есть ли между точками шашка?}
var ok:boolean;
    n,x,y:byte;
    dx,dy:shortint;
begin
  x:=x1;
  y:=y1;
  n:=0;
  ok:=false;
  if (x2=x1)or(y2=y1) then
  begin
    exist:=0;
    exit;
  end;
  dx:=abs(x2-x1) div (x2-x1);
  dy:=abs(y2-y1) div (y2-y1);
  repeat
    x:=x+dx;
    y:=y+dy;
    if mas[y,x]<>'n' then inc(n);
    if ((color=black)and(mas[y,x] in blacks))or
       ((color=white)and(mas[y,x] in whites)) then
    begin
      ok:=true;
      bx:=x;
      by:=y;
    end;
  until(abs(x-x2)=1)and(abs(y-y2)=1);
  if (ok=true)and(n=1) then exist:=1 else
  begin
    if n=0 then exist:=0 else
      exist:=2;
  end;
end; {ok}
{---------------------------------------------------------------------------}
function canbeat(var x1,y1:byte;d,r:byte;var mas:chessboard):boolean;
var bx,by,x2,y2:byte;
    ch:char;
begin
  x2:=x1+r*dir[d,1];
  y2:=y1+r*dir[d,2];
  if (between(x1,y1))and(between(x2,y2)) then
  begin
    ch:=mas[y1,x1];
    if ch in whites then
      begin
        if (r=2)or((r>2)and(ch='W')) then
        if mas[y2,x2]='n' then
        if exist(x1,y1,x2,y2,bx,by,white,mas)=1 then
        begin
          canbeat:=true;
          mas[y1,x1]:='n';
          mas[by,bx]:='n';
          if y2=1 then mas[y2,x2]:='W' else
                       mas[y2,x2]:=ch;
          x1:=x2;
          y1:=y2;
          exit;
        end;
      end else
    if ch in blacks then
      begin
        if (r=2)or((r>2)and(ch='B')) then
        if mas[y2,x2]='n' then
        if exist(x1,y1,x2,y2,bx,by,white,mas)=1 then
        begin
          canbeat:=true;
          mas[y1,x1]:='n';
          mas[by,bx]:='n';
          if y2=y0 then mas[y2,x2]:='B' else
                        mas[y2,x2]:=ch;
          x1:=x2;
          y1:=y2;
          exit;
        end;
      end;
  end;
  canbeat:=false;
end;
{---------------------------------------------------------------------------}
function compare(mas1,mas2:chessboard):shortint;
var x,y,score1,score2:shortint;
    b0,w0,db0,dw0,b,w,db,dw:byte;
begin
  for y:=1 to y0 do
  for x:=1 to x0 do
  begin
    if mas1[y,x] in whites then
    begin
      if dangerousposition(x,y,mas1,white)=true then inc(score1) else
                                                     dec(score1);
      if mas1[y,x]='w' then
      begin
        inc(w0);
        if (y=2)and(dangerousposition(x,y,mas1,white)=false) then dec(score1);
      end;
      if mas1[y,x]='W' then inc(dw0);
    end else
    if mas1[y,x] in blacks then
    begin
      if dangerousposition(x,y,mas1,black)=true then dec(score1) else
                                                     inc(score1);
      if mas1[y,x]='b' then
      begin
        inc(b0);
        if (y=y0-1)and(dangerousposition(x,y,mas1,black)=false) then inc(score1);
      end;
      if mas1[y,x]='B' then inc(db0);
    end else
    if mas2[y,x] in whites then
    begin
      if dangerousposition(x,y,mas2,white)=true then inc(score2) else
                                                     dec(score2);
      if mas2[y,x]='w' then
      begin
        inc(w);
        if (y=2)and(dangerousposition(x,y,mas1,white)=false) then dec(score2);
      end;
      if mas2[y,x]='W' then inc(dw);
    end else
    if mas2[y,x] in blacks then
    begin
      if dangerousposition(x,y,mas2,black)=true then dec(score2) else
                                                     inc(score2);
      if mas1[y,x]='b' then
      begin
        inc(b0);
        if (y=y0-1)and(dangerousposition(x,y,mas2,black)=false) then inc(score2);
      end;
      if mas1[y,x]='B' then inc(db0);
    end;
  end;
  compare:=(w0-w+2*(dw0-dw))-(b0-b+2*(db0-db))+score2-score1;
end;
{---------------------------------------------------------------------------}
function SeeBeat:boolean;
var x,y,x1,y1,d,count,d1,r,r1,bx,by:byte;
    optimum,try:array [0..10,1..2] of byte;
    maxscore,score:shortint;
    rnd:integer;
    eob{end of beat}:boolean;
    ok,damka,canbeat:boolean;
label lb,here;
begin
  ok:=false;
  randomize;
  maxscore:=-100;
  for y:=1 to y0 do
  for x:=1 to x0 do
   if field[y,x]='b' then
     begin
       canbeat:=false;
       for d:=1 to 4 do
          if between(x+2*dir[d,1],y+2*dir[d,2])and
             (field[y+dir[d,2],x+dir[d,1]] in whites)and
             (field[y+2*dir[d,2],x+2*dir[d,1]]='n') then canbeat:=true;
       if canbeat=true then
       for rnd:=1 to maxrnd do
       begin
         for d:=1 to 10 do try[d,1]:=0;
         try[0,1]:=x;
         try[0,2]:=y;
         x1:=x;
         y1:=y;
         count:=0;
         model:=field;
         score:=0;
         damka:=false;
         repeat
           {if model[y1,x1]='B' then goto here;}
           d:=random(4)+1;
           if (model[y1+dir[d,2],x1+dir[d,1]] in whites)and
              (model[y1+2*dir[d,2],x1+2*dir[d,1]]='n')and
              (between(x1+2*dir[d,1],y1+2*dir[d,2])) then
              begin
                ok:=true;
                inc(count);
                try[count,1]:=d;
                try[count,2]:=2;
                if (model[y1+dir[d,2],x1+dir[d,1]]='W')or(y1+dir[d,2]=2) then inc(score,2);
                model[y1+dir[d,2],x1+dir[d,1]]:='n';
                if y1+2*dir[d,2]=y0 then model[y1+2*dir[d,2],x1+2*dir[d,1]]:='B' else
                                         model[y1+2*dir[d,2],x1+2*dir[d,1]]:=model[y1,x1];
                model[y1,x1]:='n';
                x1:=x1+2*dir[d,1];
                y1:=y1+2*dir[d,2];
                if (y1=y0)and(damka=false) then
                begin
                  inc(score,2);
                  damka:=true;
                end;
                eob:=true;
                if model[y1,x1]='b' then
                begin
                  for d:=1 to 4 do
                  if (x1+2*dir[d,1] in [1..x0])and
                     (y1+2*dir[d,2] in [1..y0])and
                     (model[y1+dir[d,2],x1+dir[d,1]] in whites)and
                     (model[y1+2*dir[d,2],x1+2*dir[d,1]]='n') then eob:=false;
                end else
                if model[y1,x1]='B' then
                begin
                  for r:=2 to x0-1 do
                  for d:=1 to 4 do
                  if (x1+r*dir[d,1] in [1..x0])and
                     (y1+r*dir[d,2] in [1..y0])and
                     (model[y1+r*dir[d,2],x1+r*dir[d,1]]='n')and
                     (exist(x1,y1,x1+r*dir[d,1],y1+r*dir[d,2],bx,by,white,model)=1) then
                     begin
                       eob:=false;
                       goto here;
                     end;
                end;
              end;
         until eob=true;
         if eob=true then
         begin
           inc(score,count);
           if usebase then
           begin
             if search('goodbase.dat',getstring(model))=true then score:=score+3 else
             if search('badbase.dat',getstring(model))=true then score:=score-3;
           end;
           if dangerousposition(x1,y1,model,black)=false then inc(score);
           if score>maxscore then
           begin
             maxscore:=score;
             optimum:=try;
           end;
         end;
       end;
     end else
    if field[y,x]='B' then
     begin
       canbeat:=false;
       for r:=2 to x0-1 do
       for d:=1 to 4 do
         if between(x+r*dir[d,1],y+r*dir[d,2])and
            (field[y+r*dir[d,2],x+r*dir[d,1]]='n')and
            (exist(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,white,field)=1) then
            begin
              canbeat:=true;
              break;
              break;
            end;
       if canbeat=true then
       for rnd:=1 to 1000 do
       begin
         for d:=1 to 10 do
         for r:=1 to 2 do
           try[d,r]:=0;
         try[0,1]:=x;
         try[0,2]:=y;
         x1:=x;
         y1:=y;
         count:=0;
         model:=field;
         if dangerousposition(x,y,field,black)=true then score:=1 else score:=0;
         repeat
           here:
           r:=random(x0-2)+2;
           d:=random(4)+1;
           if between(x1+r*dir[d,1],y1+r*dir[d,2])and
              (model[y1+r*dir[d,2],x1+r*dir[d,1]]='n')and
              (exist(x1,y1,x1+r*dir[d,1],y1+r*dir[d,2],bx,by,white,model)=1) then
             begin
               ok:=true;
               inc(count);
               try[count,1]:=d;
               try[count,2]:=r;
               model[y1,x1]:='n';
               if by=2 then
               if model[by,bx]='w' then inc(score,1);
               if (by=2)or(model[by,bx]='W') then inc(score,2);
               model[by,bx]:='n';
               model[y1+r*dir[d,2],x1+r*dir[d,1]]:='B';
               x1:=x1+r*dir[d,1];
               y1:=y1+r*dir[d,2];
             end;
           eob:=true;
           for r:=2 to maximum(x1,y1) do
           for d:=1 to 4 do
             if between(x1+r*dir[d,1],y1+r*dir[d,2])and
                (model[y1+r*dir[d,2],x1+r*dir[d,1]]='n')and
                (exist(x1,y1,x1+r*dir[d,1],y1+r*dir[d,2],bx,by,white,model)=1) then eob:=false;
         until eob=true;
         if eob=true then
         begin
           inc(score,count);
           if usebase then
           begin
             if search('goodbase.dat',getstring(model))=true then score:=score+3 else
             if search('badbase.dat',getstring(model))=true then score:=score-3;
           end;
           if dangerousposition(x1,y1,model,black)=false then inc(score);
           if score>maxscore then
           begin
             maxscore:=score;
             optimum:=try;
           end;
         end;
       end;
     end;
  if ok=true then
  begin
    windowoff(274-textwidth(msg) div 2-10,443-36,false);
    hod:=true;
    count:=0;
    x:=optimum[0,1];
    y:=optimum[0,2];
    repeat
      inc(count);
      d:=optimum[count,1];
      r:=optimum[count,2];
      if (optimum[count+1,1]=0)and(field[y,x]='B') then
      begin
        for r:=2 to x0-1 do
        begin
          if (x+r*dir[d,1] in [1..x0])and(y+r*dir[d,2] in [1..y0])and
             (field[y+r*dir[d,2],x+r*dir[d,1]]='n')and
             (exist(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,white,field)=1)and
             (dangerousbeat(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,field,black)=false) then
             begin
               field[y,x]:='n';
               field[y+r*dir[d,2],x+r*dir[d,1]]:='B';
               square(x,y,brown);
               draughtsman((x+r*dir[d,1])*width+width div 2,(y+r*dir[d,2])*width+width div 2,true,getcolor(black));
               away(bx,by);
               writeaction(x,y,x+r*dir[d,1],y+r*dir[d,2],black);
               draughtbeat(white);
               effect;
               exit;
             end;
        end;
        goto lb;
      end else
      begin
        lb:
        d:=optimum[count,1];
        r:=optimum[count,2];
        if y+r*dir[d,2]=y0 then field[y+r*dir[d,2],x+r*dir[d,1]]:='B' else
                                field[y+r*dir[d,2],x+r*dir[d,1]]:=field[y,x];
        field[y,x]:='n';
        square(x,y,brown);
        x:=x+r*dir[d,1];
        y:=y+r*dir[d,2];
        case field[y,x] of 'B':draughtsman(x*width+width div 2,y*width+width div 2,true,getcolor(black));
                           'b':draughtsman(x*width+width div 2,y*width+width div 2,false,getcolor(black));
                        end;
        exist(x,y,x-r*dir[d,1],y-r*dir[d,2],bx,by,white,field);
        away(bx,by);
        writeaction(x-r*dir[d,1],y-r*dir[d,2],x,y,black);
        draughtbeat(white);
        effect;
      end;
    until optimum[count+1,1]=0;
  end;
end;
{---------------------------------------------------------------------------}
function VirtualBlackBeat:shortint;
var x,y,x1,y1,d,count,d1,r:byte;
    mas:chessboard;
    optimum,try:array [1..10] of byte;
    maxscore,score:byte;
    rnd:longint;
    eob{end of beat}:boolean;
    ok,damka,canbeat:boolean;
label lb;
begin
  ok:=false;
  randomize;
  maxscore:=0;
  virtualblackbeat:=0;
  for y:=1 to y0 do
  for x:=1 to x0 do
  if model[y,x]='b' then
     begin
       canbeat:=false;
       for d:=1 to 4 do
          if between(x+2*dir[d,1],y+2*dir[d,2])and
             (model[y+2*dir[d,2],x+2*dir[d,1]]='n')and
             (model[y+dir[d,2],x+dir[d,1]] in whites) then
            begin
              canbeat:=true;
              break;
            end;
       if canbeat=true then
       for rnd:=1 to maxrnd do
       begin
         for d:=1 to 10 do try[d]:=0;
         try[1]:=x;
         try[2]:=y;
         x1:=x;
         y1:=y;
         count:=2;
         mas:=model;
         score:=0;
         damka:=false;
         repeat
           d:=random(4)+1;
           if between(x1+2*dir[d,1],y1+2*dir[d,2]) then
           if (mas[y1+2*dir[d,2],x1+2*dir[d,1]]='n') then
           if (mas[y1+dir[d,2],x1+dir[d,1]] in whites) then
              begin
                ok:=true;
                inc(count);
                try[count]:=d;
                mas[y1,x1]:='n';
                if mas[y1+dir[d,2],x1+dir[d,1]]='W' then inc(score,2);
                mas[y1+dir[d,2],x1+dir[d,1]]:='n';
                mas[y1+2*dir[d,2],x1+2*dir[d,1]]:='b';
                x1:=x1+2*dir[d,1];
                y1:=y1+2*dir[d,2];
                if (y1=y0)and(damka=false) then
                begin
                  inc(score,2);
                  damka:=true;
                end;
                eob:=true;
                for d:=1 to 4 do
                if between(x1+2*dir[d,1],y1+2*dir[d,2]) then
                if (mas[y1+2*dir[d,2],x1+2*dir[d,1]]='n') then
                if (mas[y1+dir[d,2],x1+dir[d,1]] in whites) then
                begin
                  eob:=false;
                  break;
                end;
              end;
         until eob=true;
         if eob=true then
         begin
           inc(score,count-2);
           if dangerousposition(x1,y1,mas,black)=false then inc(score);
           if score>maxscore then
           begin
             maxscore:=score;
             optimum:=try;
           end;
         end;
       end;
     end;
  if (ok=true) then
  begin
    count:=2;
    x:=optimum[1];
    y:=optimum[2];
    repeat
      inc(count);
      if optimum[count]>=1 then
        begin
          d:=optimum[count];
          if (optimum[count+1]=0)and(model[y,x]='B') then
          begin
            for r:=2 to x0-1 do
            if (x+r*dir[d,1] in [1..x0]) then
            if (y+r*dir[d,2] in [1..y0]) then
            if (model[y+r*dir[d,2],x+r*dir[d,1]]='n') then
            if (dangerousbeat(x,y,x+r*dir[d,1],y+r*dir[d,2],x+dir[d,1],y+dir[d,2],model,black)=false) then
               begin
                 model[y,x]:='n';
                 model[y+dir[d,2],x+dir[d,1]]:='n';
                 model[y+r*dir[d,2],x+r*dir[d,1]]:='B';
                 virtualblackbeat:=maxscore;
                 exit;
               end;
            goto lb;
          end else
          begin
            lb:
            if (y+2*dir[d,2]=y0) then model[y+2*dir[d,2],x+2*dir[d,1]]:='B' else
                                      model[y+2*dir[d,2],x+2*dir[d,1]]:=model[y,x];
            model[y,x]:='n';
            model[y+dir[d,2],x+dir[d,1]]:='n';
            x:=x+2*dir[d,1];
            y:=y+2*dir[d,2];
          end;
        end;
    until optimum[count+1]=0;
  end else maxscore:=0;
  virtualblackbeat:=maxscore;
end;
{---------------------------------------------------------------------------}
function VirtualWhiteBeat:shortint;
var x,y,x1,y1,d,count,d1,r:byte;
    mas:chessboard;
    optimum,try:array [1..10] of byte;
    maxscore,score:byte;
    rnd:longint;
    eob{end of beat}:boolean;
    ok,damka,canbeat:boolean;
label lb;
begin
  ok:=false;
  randomize;
  maxscore:=0;
  virtualwhitebeat:=0;
  for y:=1 to y0 do
  for x:=1 to x0 do
    if model[y,x]='w' then
     begin
       canbeat:=false;
       for d:=1 to 4 do
          if between(x+2*dir[d,1],y+2*dir[d,2]) then
          if (model[y+2*dir[d,2],x+2*dir[d,1]]='n') then
          if (model[y+dir[d,2],x+dir[d,1]] in blacks) then canbeat:=true;
       if canbeat=true then
       for rnd:=1 to maxrnd do
       begin
         for d:=1 to 10 do try[d]:=0;
         try[1]:=x;
         try[2]:=y;
         x1:=x;
         y1:=y;
         count:=2;
         mas:=model;
         score:=0;
         damka:=false;
         repeat
           d:=random(4)+1;
           if between(x1+2*dir[d,1],y1+2*dir[d,2]) then
           if (mas[y1+2*dir[d,2],x1+2*dir[d,1]]='n') then
           if (mas[y1+dir[d,2],x1+dir[d,1]] in blacks) then
              begin
                ok:=true;
                inc(count);
                try[count]:=d;
                mas[y1,x1]:='n';
                if mas[y1+dir[d,2],x1+dir[d,1]]='B' then inc(score,2);
                mas[y1+dir[d,2],x1+dir[d,1]]:='n';
                mas[y1+2*dir[d,2],x1+2*dir[d,1]]:='w';
                x1:=x1+2*dir[d,1];
                y1:=y1+2*dir[d,2];
                if (y1=1)and(damka=false) then
                begin
                  inc(score,2);
                  damka:=true;
                end;
                eob:=true;
                for d:=1 to 4 do
                if between(x1+2*dir[d,1],y1+2*dir[d,2]) then
                if (mas[y1+2*dir[d,2],x1+2*dir[d,1]]='n') then
                if (mas[y1+dir[d,2],x1+dir[d,1]] in blacks) then eob:=false;
              end;
         until eob=true;
         if eob=true then
         begin
           inc(score,count-2);
           if dangerousposition(x1,y1,mas,white)=false then inc(score,2);
           if score>maxscore then
           begin
             maxscore:=score;
             optimum:=try;
           end;
         end;
       end;
     end;
  if (ok=true) then
  begin
    count:=2;
    x:=optimum[1];
    y:=optimum[2];
    repeat
      inc(count);
      if optimum[count]>=1 then
        begin
          d:=optimum[count];
          if (optimum[count+1]=0)and(model[y,x]='W') then
          begin
            for r:=2 to x0 do
            if between(x+r*dir[d,1],y+r*dir[d,2]) then
            if (model[y+r*dir[d,2],x+r*dir[d,1]]='n') then
            if (dangerousbeat(x,y,x+r*dir[d,1],y+r*dir[d,2],x+dir[d,1],y+dir[d,2],model,white)=false) then
               begin
                 model[y,x]:='n';
                 model[y+dir[d,2],x+dir[d,1]]:='n';
                 model[y+r*dir[d,2],x+r*dir[d,1]]:='W';
                 virtualwhitebeat:=maxscore;
                 exit;
               end;
               goto lb;
          end else
          begin
            lb:
            if (y+2*dir[d,2]=1) then model[y+2*dir[d,2],x+2*dir[d,1]]:='W' else
                                     model[y+2*dir[d,2],x+2*dir[d,1]]:=model[y,x];
            model[y,x]:='n';
            model[y+dir[d,2],x+dir[d,1]]:='n';
            x:=x+2*dir[d,1];
            y:=y+2*dir[d,2];
          end;
        end;
    until optimum[count+1]=0;
  end else maxscore:=0;
  virtualwhitebeat:=maxscore;
end;
{---------------------------------------------------------------------------}
function OneBeat(mas:chessboard):boolean;
var x,y,d,r,bx,by:byte;
    first:boolean;
begin
  first:=false;
  onebeat:=true;
  for y:=1 to y0 do
  for x:=1 to x0 do
    if (mas[y,x] in blacks) then
      begin
        for d:=1 to 4 do
        for r:=1 to maximum(x,y) do
        if between(x-dir[d,1],y-dir[d,2]) then
        if between(x+r*dir[d,1],y+r*dir[d,2]) then
        if (mas[y-dir[d,2],x-dir[d,1]]='n') then
        if (((r=1)and(mas[y+dir[d,2],x+dir[d,1]]='w'))or
            (mas[y+r*dir[d,2],x+r*dir[d,1]]='W'))and
           ((r=1)or((r>1)and(freeway(x,y,x+r*dir[d,1],y+r*dir[d,2],mas)=true))) then
                    begin
                      if first=true then
                      begin
                        onebeat:=false;
                        exit;
                      end else
                      begin
                        first:=true;
                        break;
                      end;
                    end;
      end;
end;
{---------------------------------------------------------------------------}
function Number(color:word;mas:chessboard):byte;
var x,y,b,w:byte;
begin
  b:=0;
  w:=0;
  number:=0;
  for y:=1 to y0 do
  for x:=1 to x0 do
    if mas[y,x] in blacks then inc(b) else
    if mas[y,x] in whites then inc(w);
  case color of black:number:=b;
                white:number:=w;
             end;
end; {ok}
{---------------------------------------------------------------------------}
procedure Combination;
var x,y,d,sx,sy,sd:byte;
    score,maxscore,delta:shortint;
begin
  maxscore:=-100;
  if number(black,field)>1 then
  begin
  for y:=1 to y0 do
  for x:=1 to x0 do
    if field[y,x]='b' then
      for d:=1 to 2 do
      if (x+2*dir[d,1] in [1..x0]) then
      if (y+2*dir[d,2] in [1..y0]) then
      if (field[y+dir[d,2],x+dir[d,1]]='n') then
      if (field[y+2*dir[d,2],x+2*dir[d,1]] in whites) then
        begin
          score:=0;
          model:=field;
          model[y,x]:='n';
          model[y+dir[d,2],x+dir[d,1]]:='b';
          if onebeat(model)=true then
          begin
            for depth:=1 to depth0 do
            begin
              delta:=virtualwhitebeat;
              if delta<>0 then score:=score-delta else break;
              delta:=virtualblackbeat;
              if delta<>0 then score:=score+delta else break;
            end;
            if (score>maxscore) then
            begin
              sx:=x;
              sy:=y;
              sd:=d;
              maxscore:=score;
            end;
          end;
        end;
    if (maxscore>2)and(number(black,field)>1) then
    begin
      windowoff(274-textwidth(msg) div 2-10,443-36,false);
      hod:=true;
      field[sy,sx]:='n';
      field[sy+dir[sd,2],sx+dir[sd,1]]:='b';
      square(sx,sy,brown);
      draughtsman((sx+dir[sd,1])*width+width div 2,(sy+dir[sd,2])*width+width div 2,false,getcolor(black));
      writeaction(sx,sy,sx+dir[sd,1],sy+dir[sd,2],black);
      effect;
    end;
  end;
end;
{---------------------------------------------------------------------------}
function danger(color:word;mas:chessboard):boolean;
var x,y:byte;
begin
  danger:=false;
  for y:=1 to y0 do
  for x:=1 to x0 do
  if x mod 2<> y mod 2 then
  if (((color=black)and(mas[y,x] in blacks))or
      ((color=white)and(mas[y,x] in whites)))and
     (dangerousposition(x,y,mas,color)=true) then
    begin
      danger:=true;
      exit;
    end;
end; {ok}
{---------------------------------------------------------------------------}
function neighbour(x,y:byte;mas:chessboard):boolean;
var d:byte;
begin
  neighbour:=false;
  for d:=3 to 4 do
  if (between(x+2*dir[d,1],y+2*dir[d,2]))and
     (mas[y+dir[d,2],x+dir[d,1]]='n')and((mas[y+2*dir[d,2],x+2*dir[d,1]] in blacks)or(mas[y-2,x] in blacks))or
     (x in [1,x0])or(y in [1,y0]) then neighbour:=true;
end;
{---------------------------------------------------------------------------}
function side(x,y:byte;mas:chessboard):boolean;
begin
  side:=false;
  if y+2<=y0 then
  begin
    if x=2 then
    begin
      if mas[y+2,2] in whites then
      if mas[y+1,1]='n' then
        side:=true;
    end else
    if x=x0-1 then
    begin
      if mas[y+2,x] in whites then
      if mas[y+1,x0]='n' then
        side:=true;
    end;
  end;
end; {ok}
{---------------------------------------------------------------------------}
procedure Action;
var x,y,x1,y1,x2,y2,bx,by,r,d:byte;
    score,maxscore:real;
    result,WhiteDanger,WasSide:boolean;
    rnd:integer;
    delta:shortint;
begin
  randomize;
  maxscore:=-100;
  for y:=1 to y0 do
  for x:=1 to x0 do
    begin
      if field[y,x]='b' then
        begin
          for d:=1 to 2 do
          begin
            score:=0;
            model:=field;
            if between(x+dir[d,1],y+dir[d,2]) then
            if (model[y+dir[d,2],x+dir[d,1]]='n') then
              begin
                wasside:=side(x,y,model)=true;
                result:=danger(black,model);
                model[y,x]:='n';
                model[y+dir[d,2],x+dir[d,1]]:='b';
                if neighbour(x+dir[d,1],y+dir[d,2],model)=true then score:=score+0.5;
                if wasside=true then
                if side(x+dir[d,1],y+dir[d,2],model)=false then score:=score+1;
                if y+dir[d,2]=y0 then score:=score+2;
                if (result=true)and(danger(black,model)=false) then score:=score+1;
                if dangerousposition(x+dir[d,1],y+dir[d,2],model,black)=false then score:=score+1.5 else score:=score-2;
                if usebase then
                begin
                  if search('goodbase.dat',getstring(model))=true then score:=score+3;
                  if search('badbase.dat',getstring(model))=true then score:=score-3;
                end;
                for depth:=1 to depth0 do
                begin
                  delta:=virtualwhitebeat;
                  if delta<>0 then score:=score-delta else break;
                  delta:=virtualblackbeat;
                  if delta<>0 then score:=score+delta else break;
                end;
                if (score>maxscore)or((score=maxscore)and(random(2)=1)) then
                begin
                  hod:=true;
                  maxscore:=score;
                  x1:=x;
                  y1:=y;
                  x2:=x+dir[d,1];
                  y2:=y+dir[d,2];
                end;
              end;
          end;
        end else
      if field[y,x]='B' then
        begin
          for rnd:=1 to maxrnd do
            begin
              r:=random(x0-2)+1;
              d:=random(4)+1;
              model:=field;
              score:=0;
              if between(x+r*dir[d,1],y+r*dir[d,2]) then
              if (model[y+r*dir[d,2],x+r*dir[d,1]]='n') then
              if (exist(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,white,model)=0) then
                begin
                  hod:=true;
                  whitedanger:=danger(white,model);
                  result:=danger(black,model);
                  model[y,x]:='n';
                  model[y+r*dir[d,2],x+r*dir[d,1]]:='B';
                  if (whitedanger=false)and(danger(white,model)=true)and
                     (dangerousposition(x+r*dir[d,1],y+r*dir[d,2],model,black)=false)and
                     (danger(black,model)=false) then score:=score+1 else
                  if (whitedanger=false)and(danger(white,model)=true)and
                     (dangerousposition(x+r*dir[d,1],y+r*dir[d,2],model,black)=false) then score:=score+1;
                  if (danger(black,model)=false)and(dangerousposition(x+r*dir[d,1],y+r*dir[d,2],model,black)=false) then
                      score:=score+1;
                  if (result=true)and(danger(black,model)=false) then score:=score+2;
                  if (dangerousposition(x+r*dir[d,1],y+r*dir[d,2],model,black)=true) then score:=score-3;
                  if usebase then
                  begin
                    if search('goodbase.dat',getstring(model))=true then score:=score+3;
                    if search('badbase.dat',getstring(model))=true then score:=score-3;
                  end;
                  for depth:=1 to depth0 do
                  begin
                    delta:=virtualwhitebeat;
                    if delta<>0 then score:=score-delta else break;
                    delta:=virtualblackbeat;
                    if delta<>0 then score:=score+delta else break;
                  end;
                  if score>maxscore then
                  begin
                    maxscore:=score;
                    x1:=x;
                    y1:=y;
                    x2:=x+r*dir[d,1];
                    y2:=y+r*dir[d,2];
                  end;
                end;
            end;
        end;
    end;
  if hod=true then
  begin
    windowoff(274-textwidth(msg) div 2-10,443-36,false);
    square(x1,y1,brown);
    if (y2=y0)or(field[y1,x1]='B') then
      begin
        field[y2,x2]:='B';
        draughtsman(x2*width+width div 2,y2*width+width div 2,true,getcolor(black));
      end else
      begin
        field[y2,x2]:='b';
        draughtsman(x2*width+width div 2,y2*width+width div 2,false,getcolor(black));
      end;
    field[y1,x1]:='n';
    writeaction(x1,y1,x2,y2,black);
    effect;
  end;
end;
{---------------------------------------------------------------------------}
procedure Computer;
const max=38;
var score:shortint;
    n:byte;
    rnd:byte;
    f:text;
begin
  {$I-}
  assign(f,'message.txt');
  reset(f);
  if ioresult=0 then
  begin
    rnd:=random(max)+1;
    for n:=1 to rnd do readln(f,msg);
    message;
  end;
  close(f);
  {$I+}
  blackfield:=field;
  hod:=false;
  seebeat;
  if (hod=false)and(endofgame=false) then combination;
  if (hod=false)and(endofgame=false) then action;
  if hod=false then windowoff(274-textwidth(msg) div 2-10,443-36,false);
  roll(blackstr,getstring(field));
  if blackwin then
  if appreciate(blackfield,field,black)>needtosave then
  begin
    savecombination(blackstr,'goodbase.dat');
  end;
  if whitelose then
  if appreciate(whitefield,field,white)<-needtosave then
  begin
    for n:=1 to 3 do helpstr[n]:=invertstr(whitestr[n]);
    savecombination(helpstr,'badbase.dat');
  end;
  if (hod=false)and(number(black,field)>0) then
  if onceagain(1)=false then quit;
end;
{---------------------------------------------------------------------------}
procedure Player(x1,y1,x2,y2:integer;damka:boolean);
var bx,by,n:byte;
    score:shortint;
begin
  whitefield:=field;
  if num0=1 then
  begin
    if field[y1,x1]='w' then
    begin
      if y1-y2=1 then
      begin
        field[y1,x1]:='n';
        square(x1,y1,brown);
        if y2=1 then
        begin
          field[y2,x2]:='W';
          draughtsman(x2*width+width div 2,y2*width+width div 2,true,getcolor(white));
        end else
        begin
          field[y2,x2]:='w';
          draughtsman(x2*width+width div 2,y2*width+width div 2,false,getcolor(white));
        end;
        effect;
      end else
      if abs(y1-y2)=2 then
      begin
        field[y1,x1]:='n';
        square(x1,y1,brown);
        {square((x1+x2) div 2,(y1+y2) div 2,brown);}
        if y2=1 then
        begin
          field[y2,x2]:='W';
          draughtsman(x2*width+width div 2,y2*width+width div 2,true,getcolor(white));
        end else
        begin
          field[y2,x2]:='w';
          draughtsman(x2*width+width div 2,y2*width+width div 2,false,getcolor(white));
        end;
        away((x1+x2) div 2,(y1+y2) div 2);
        field[(y1+y2) div 2,(x1+x2) div 2]:='n';
        draughtbeat(black);
        effect;
      end;
    end else
    if field[y1,x1]='W' then
    begin
      field[y1,x1]:='n';
      square(x1,y1,brown);
      draughtsman(x2*width+width div 2,y2*width+width div 2,true,getcolor(white));
      if (abs(x2-x1)>=2)and(exist(x1,y1,x2,y2,bx,by,black,field)=1) then
      begin
        away(bx,by);
        field[by,bx]:='n';
        {square(bx,by,brown);}
        draughtbeat(black);
      end;
      field[y2,x2]:='W';
      effect;
    end;
    writeaction(x1,y1,x2,y2,white);
  end else
  if num0>1 then
  begin
    if (field[y1,x1]='w') then
    for num:=0 to num0-1 do
    begin
      square(place[1,num],place[2,num],brown);
      if place[2,num+1]=1 then
      begin
        field[place[2,num+1],place[1,num+1]]:='W';
        draughtsman(place[1,num+1]*width+width div 2,place[2,num+1]*width+width div 2,true,getcolor(white));
      end else
      begin
        field[place[2,num+1],place[1,num+1]]:=field[place[2,num],place[1,num]];
        if field[place[2,num],place[1,num]]='w'  then
          draughtsman(place[1,num+1]*width+width div 2,place[2,num+1]*width+width div 2,false,getcolor(white)) else
          draughtsman(place[1,num+1]*width+width div 2,place[2,num+1]*width+width div 2,true,getcolor(white))
      end;
      field[place[2,num],place[1,num]]:='n';
      if damka=true then
      begin
        if exist(place[1,num],place[2,num],place[1,num+1],place[2,num+1],bx,by,black,field)=1 then
        away(bx,by);
        field[by,bx]:='n';
      end else
      begin
        away((place[1,num]+place[1,num+1]) div 2,(place[2,num]+place[2,num+1]) div 2);
        field[(place[2,num]+place[2,num+1]) div 2,(place[1,num]+place[1,num+1]) div 2]:='n';
      end;
      writeaction(place[1,num],place[2,num],place[1,num+1],place[2,num+1],white);
      draughtbeat(black);
      effect;
    end else
    if field[y1,x1]='W' then
    for num:=0 to num0-1 do
    begin
      field[place[2,num],place[1,num]]:='n';
      square(place[1,num],place[2,num],brown);
      field[place[2,num+1],place[1,num+1]]:='W';
      draughtsman(place[1,num+1]*width+width div 2,place[2,num+1]*width+width div 2,true,getcolor(white));
      if exist(place[1,num],place[2,num],place[1,num+1],place[2,num+1],bx,by,black,field)=1 then
      begin
        away(bx,by);
        field[by,bx]:='n';
        draughtbeat(black);
      end;
      writeaction(place[1,num],place[2,num],place[1,num+1],place[2,num+1],white);
      effect;
    end;
  end;
  roll(whitestr,getstring(field));
  if whitewin then
  if appreciate(whitefield,field,white)>needtosave then
  begin
    for n:=1 to 3 do helpstr[n]:=invertstr(whitestr[n]);
    savecombination(helpstr,'goodbase.dat');
  end;
  if whitelose then
  if appreciate(blackfield,field,black)<-needtosave then
  begin
    savecombination(blackstr,'badbase.dat');
  end;
end;
{---------------------------------------------------------------------------}
function GreenLight(x,y:byte):boolean;
var x1,y1,d,r,bx,by:byte;
    MaxR:byte;
begin
  mustbeat:=true;
  greenlight:=false;
  if danger(black,field)=true then
  begin
    case field[y,x] of 'w':maxr:=2;
                       'W':maxr:=maximum(x,y);
                    end;
    for r:=2 to maxr do
    for d:=1 to 4 do
      if between(x+r*dir[d,1],y+r*dir[d,2]) then
      if field[y+r*dir[d,2],x+r*dir[d,1]]='n' then
      if exist(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,black,field)=1 then
      begin
        mustbeat:=false;
        break;
        break;
      end;
  end else
  mustbeat:=false;
  if mustbeat=false then
  begin
    greenlight:=true;
    exit;
  end else
  if remind=true then
  begin
    for x1:=63 downto 1 do
    begin
      if soundeffect=true then sound(100*x1);
      setrgbpalette(red,63,x1,22);
      delay(round(pause));
    end;
    for x1:=2 to 63 do
    begin
      if soundeffect=true then sound(100*x1);
      setrgbpalette(red,63,x1,22);
      delay(round(pause));
    end;
    nosound;
  end;
end;
{---------------------------------------------------------------------------}
procedure breaking(st1,st2:string);
const color=red;
var n,n0,x0,y0:integer;
    mas:array [1..1500,1..2] of integer;
    k1,k2:real;
label lb1,lb2;
begin
  n:=0;
  x0:=getmaxx;
  y0:=getmaxy;
  outtextxy(x0 div 2,y0 div 2-10,st1);
  for y:=y0 div 2-10-textheight(st1) to y0 div 2-10+textheight(st1) do
  for x:=(x0-textwidth(st1)) div 2 to (x0+textwidth(st1)) div 2 do
  if getpixel(x,y)=color then
  begin
    inc(n);
    mas[n,1]:=x;
    mas[n,2]:=y;
    if keypressed then
    begin
      readkey;
      next1:=true;
      exit;
    end;
  end;
  delay(round(5000*pause));
  n0:=n;
  for a:=1 to 100 do
  begin
    if st2='' then
    {setrgbpalette(color,64-(63*a) div 100,64-(63*a) div 100,64-(63*a) div 100);}
    for n:=1 to n0 do
    begin
      putpixel(mas[n,1],mas[n,2],black);
      k1:=random(100)/(100*a);
      k2:=random(100)/(100*a);
      putpixel(round(mas[n,1]+(mas[n,1]-x0 div 2)*k1),round(mas[n,2]+(mas[n,2]-y0 div 2)*k2),color);
      mas[n,1]:=round(mas[n,1]+(mas[n,1]-x0 div 2)*k1);
      mas[n,2]:=round(mas[n,2]+(mas[n,2]-y0 div 2)*k2);
      if keypressed then
      begin
        readkey;
        next1:=true;
        exit;
      end;
    end;
  end;
  for a:=100 downto round(length(st2)/3) do
  begin
    {setrgbpalette(color,64-(63*a) div 100,64-(63*a) div 100,64-(63*a) div 100);}
    if st2<>'' then
    for n:=1 to n0 do
    begin
      putpixel(mas[n,1],mas[n,2],black);
      k1:=random(100)/(100*a);
      k2:=random(100)/(100*a);
      putpixel(round(mas[n,1]-(mas[n,1]-x0 div 2)*k1),round(mas[n,2]-(mas[n,2]-y0 div 2)*k2),color);
      mas[n,1]:=round(mas[n,1]-(mas[n,1]-x0 div 2)*k1);
      mas[n,2]:=round(mas[n,2]-(mas[n,2]-y0 div 2)*k2);
      if keypressed then
      begin
        next1:=true;
        exit;
      end;
    end;
  end;
  cleardevice;
  setrgbpalette(color,63,63,63);
  outtextxy(x0 div 2,y0 div 2-10,st2);
end;
{---------------------------------------------------------------------------}
procedure screen;
const st1='Dugin';
      st2='Andrew';
      st3='presents';
      st4='Draughts';
      color=red;
var x,y,n,x0,y0,n0,a,x1,y1:integer;
    mas:array [1..2000,1..2] of integer;
    k1,k2:real;
    l:longint;
label lb1,lb2;
begin
  randomize;
  x0:=getmaxx;
  y0:=getmaxy;
  setcolor(color);
  setrgbpalette(color,63,63,63);
  settextstyle(1,0,5);
  settextjustify(centertext,centertext);
  breaking(st1,st2);
  if next1=true then goto lb1;
  breaking(st2,st3);
  if next1=true then goto lb1;
  breaking(st3,'');
  lb1:
  clearviewport;
  setcolor(lightgray);
  outtextxy(x0 div 2,y0 div 2,st4);
  n:=0;
  for y:=y0 div 2-textheight(st4) to y0 div 2+textheight(st4) do
  for x:=(x0-textwidth(st4)) div 2-20 to (x0+textwidth(st4)) div 2+20 do
  if getpixel(x,y)=lightgray then
  begin
    inc(n);
    mas[n,1]:=x;
    mas[n,2]:=y;
  end;
  n0:=n;
  delay(3000);
  thunder;
  setcolor(color);
  outtextxy(x0 div 2,y0 div 2,st4);
  for y:=y0 div 2-textheight(st4) to y0 div 2+textheight(st4) do
  for x:=(x0-textwidth(st4)) div 2-20 to (x0+textwidth(st4)) div 2+20 do
  if getpixel(x,y)=color then
  for y1:=y-1 to y+1 do
  for x1:=x-1 to x+1 do
  if getpixel(x1,y1)=black then putpixel(x1,y1,lightblue);
  for y:=y0 div 2-textheight(st4) to y0 div 2+textheight(st4) do
  for x:=(x0-textwidth(st4)) div 2-20 to (x0+textwidth(st4)) div 2+20 do
  if getpixel(x,y)=lightblue then
  for y1:=y-1 to y+1 do
  for x1:=x-1 to x+1 do
  if getpixel(x1,y1)=black then putpixel(x1,y1,blue);
  for l:=1 to 500000 do
  begin
    n:=random(n0)+1;
    putpixel(mas[n,1],mas[n,2],random(15)+1);
    if keypressed then
    begin
      readkey;
      exit;
    end;
  end;
end;
{---------------------------------------------------------------------------}
function Continue:boolean;
var x,y,d,r,bx,by:byte;
begin
  continue:=false;
  for y:=1 to y0 do
  for x:=1 to x0 do
    if field[y,x] in whites then
    for r:=1 to x0-1 do
    for d:=1 to 4 do
      case r of 1:if (x+dir[d,1] in [1..x0])and(y+dir[d,2] in [1..y0])and
                     (field[y+dir[d,2],x+dir[d,1]]='n')and
                     (((field[y,x]='w')and(dir[d,2]=-1))or(field[y,x]='W')) then
                    begin
                      continue:=true;
                      exit;
                    end;
                2:if (x+2*dir[d,1] in [1..x0])and(y+2*dir[d,2] in [1..y0])and
                     (field[y+dir[d,2],x+dir[d,1]] in blacks)and
                     (field[y+2*dir[d,2],x+2*dir[d,1]]='n') then
                    begin
                      continue:=true;
                      exit;
                    end;
                3..x0-1:if (field[y,x]='W')and(x+r*dir[d,1] in [1..x0])and(y+r*dir[d,2] in [1..y0])and
                           (field[y+r*dir[d,2],x+r*dir[d,1]]='n')and
                           (exist(x,y,x+r*dir[d,1],y+r*dir[d,2],bx,by,black,field)=0) then
                          begin
                            continue:=true;
                            exit;
                          end;

             end;
end;
{---------------------------------------------------------------------------}
label start,again,next,new,draught,restart,functions;
begin
  difficulty:=1;
  speed:=1;
  soundeffect:=false;
  language:=1;
  pause:=0.01;
  remind:=true;
  usebase:=false;
  invertcolor:=false;
  period:=30;
  init(n1,n2);
  initgraph(a,c,'');
  disappear;
  screen;
  cleardevice;
  pause:=0.75;
  settextstyle(0,0,1);
  board(false);
  {$I-}
  assign(f,'draughts.his');
  reset(f);
  readln(f,filename);
  readln(f,pause);
  close(f);
  {$I+}
  startgame:=false;
  new:
  endofgame:=false;
  eraseall;
  situation:=0;
  setxrange(1,getmaxx-16);
  setyrange(1,getmaxy-16);
  mouseon;
  setlinestyle(solidln,0,1);
  randomize;
  stroka:=stroka0;
  xm0:=0;
  ym0:=0;
  whitefield:=field;
  blackfield:=field;
  repeat
    start:
    if startgame=true then gettime(hour,minute,second,sec100);
    restart:
    if continue=false then
    begin
      if onceagain(0)=false then quit else
      begin
        stroka:=stroka0;
        beat_w:=0;
        beat_b:=0;
        startgame:=false;
        mouseoff;
        board(true);
        mouseon;
        eraseall;
        goto new;
      end;
    end;
    repeat
      ok:=false;
      damka:=false;
      if (startgame=false)and(invertcolor=true) then
      begin
        startgame:=true;
        computer;
        setlinestyle(solidln,0,1);
      end;
      repeat
        {getmousexyondown(xm,ym,0,n2,l,r,m);}
        if commander=false then getmouseinfo(xm,ym,l,r,m);
        showtime;
        if l=false then
        if wait(hour,minute,second)=true then goto start;
      until (l=true)and((xm<>xm0)or(ym<>ym0));
      if (xm>=width)and(xm<=(x0+1)*width)and(ym>=width)and(ym<=(y0+1)*width)and
         (startgame=false) then
      begin
        startgame:=true;
        gettime(hour,minute,second,sec100);
      end;
      if (xm>=width)and(xm<=(x0+1)*width)and(ym>=width)and(ym<=(y0+1)*width)and
         ((field[ym div width,xm div width]='w')or(field[ym div width,xm div width]='W'))and
         ((greenlight(xm div width,ym div width)=true)or(remind=false))and(startgame) then
      begin
        model:=field;
        x1:=xm div width;
        y1:=ym div width;
        setcolor(cursor);
        mouseoff;
        rectangle(x1*width,y1*width,(x1+1)*width,(y1+1)*width);
        mouseon;
        xm0:=xm;
        ym0:=ym;
      end else
      begin
        functions:
        if (xm>=530)and(ym>=220)and(xm<getmaxx-10)and(ym<250) then
        begin
          buttonpress(530,220,getmaxx-10,250,'Новая игра');
          stroka:=stroka0;
          beat_w:=0;
          beat_b:=0;
          startgame:=false;
          mouseoff;
          board(true);
          mouseon;
          eraseall;
          goto new;
        end else
        if (xm>=530)and(ym>=250)and(xm<getmaxx-10)and(ym<280) then
        begin
          buttonpress(530,250,getmaxx-10,280,'Выход');
          if escape=true then quit;
        end else
        if (xm>=530)and(ym>=160)and(xm<getmaxx-10)and(ym<190) then
        begin
          buttonpress(530,160,getmaxx-10,190,'Просмотр');
          play;
        end else
        if(xm>=530)and(ym>=190)and(xm<=getmaxx-10)and(ym<=220) then
        begin
          buttonpress(530,190,getmaxx-10,220,'Развитие');
          developement(xm,ym);
        end;
        if (xm>=530)and(ym>=70)and(xm<getmaxx-10)and(ym<100)and(situation>=1) then
        begin
          buttonpress(530,70,getmaxx-10,100,'Сохранить');
          save;
        end else
        if (xm>=530)and(ym>=40)and(xm<getmaxx-10)and(ym<70) then
        begin
          xm0:=xm;
          ym0:=ym;
          buttonpress(530,40,getmaxx-10,70,'Открыть');
          load(true);
          goto start;
        end else
        if (xm>=530)and(ym>=10)and(xm<getmaxx-10)and(ym<40)and(l=true)and(situation>=1) then
        begin
          xm0:=xm;
          ym0:=ym;
          if difficulty=1 then
          begin
            buttonpress(530,10,getmaxx-10,40,'Отмена хода');
            backspace;
            goto start;
          end;
        end else
        if(xm>=530)and(ym>=100)and(xm<=getmaxx-10)and(ym<=130)and(l=true) then
        begin
          buttonpress(530,100,getmaxx-10,130,'Информация');
          information(xm,ym);
        end else
        if(xm>=530)and(ym>=130)and(xm<=getmaxx-10)and(ym<=160)and(l=true) then
        begin
          buttonpress(530,130,getmaxx-10,160,'Опции');
          options(xm,ym);
          if newboard=true then
          begin
            stroka:=stroka0;
            beat_w:=0;
            beat_b:=0;
            eraseall;
            startgame:=false;
            mouseoff;
            board(false);
            mouseon;
            newboard:=false;
            setlinestyle(solidln,0,1);
            goto new;
          end;
          setlinestyle(solidln,0,1);
        end else
        if (xm>=17)and(ym>=1)and(xm<=382)and(ym<=20) then
        begin
          buttonpress(17,1,382,20,'Автор и разработчик программы: Дугин Андрей');
          authorship(xm,ym);
        end;
      end;
      xm0:=xm;
      ym0:=ym;
    until model[y1,x1] in whites;
    if model[y1,x1]='W' then damka:=true;
    draught:
    num:=0;
    place[1,0]:=x1;
    place[2,0]:=y1;
    ok:=false;
    repeat
      again:
      repeat
        if commander=false then getmouseinfo(xm,ym,l,r,m);
        if (l=false)and(r=false) then
        begin
          showtime;
          if (wait(hour,minute,second)=true) then goto start;
        end;
      until ((l=true)or(r=true))and((xm<>xm0)or(ym<>ym0));
      if (l=true)and(between(xm div width,ym div width)=false) then
      begin
        cancel;
        num:=0;
        goto functions;
      end;
      if (between(xm div width,ym div width))and
         ((xm div width) mod 2<>(ym div width) mod 2)and
         (abs(place[1,num]-xm div width)=abs(place[2,num]-ym div width))and
         (model[ym div width,xm div width]='n') then
      begin
        if r=true then
        begin
          if (model[y1,x1]='w')and(abs(place[2,num]-ym div width)=2)and
             (model[(place[2,num]+ym div width) div 2,(place[1,num]+xm div width) div 2] in blacks) then
          begin
            inc(num);
            xm0:=xm;
            ym0:=ym;
            if ym div width=1 then damka:=true;
            place[1,num]:=xm div width;
            place[2,num]:=ym div width;
            setcolor(lightgreen);
            mouseoff;
            rectangle((xm div width)*width,(ym div width)*width,(xm div width+1)*width,(ym div width+1)*width);
            mouseon;
            goto again;
          end else
          if ((model[y1,x1]='W')or(damka=true))and
             (exist(place[1,num],place[2,num],xm div width,ym div width,bx,by,black,model)=1) then
          begin
            inc(num);
            xm0:=xm;
            ym0:=ym;
            place[1,num]:=xm div width;
            place[2,num]:=ym div width;
            setcolor(lightgreen);
            mouseoff;
            rectangle((xm div width)*width,(ym div width)*width,(xm div width+1)*width,(ym div width+1)*width);
            mouseon;
            goto again;
          end;
        end else
        if (l=true)and((xm div width<>place[1,num])and(ym div width<>place[2,num])) then
          begin
            permission:=false;
            if (model[y1,x1]='w')and(damka=false) then
            begin
              case place[2,num]-ym div width of 1:if num=0 then
                                                  begin
                                                    permission:=true;
                                                    goto next;
                                                   end else goto again;
                                             -2,2:if (model[(place[2,num]+ym div width) div 2,
                                                     (place[1,num]+xm div width) div 2] in blacks) then
                                                   begin
                                                     permission:=true;
                                                     goto next;
                                                   end else goto again;
                                             end;
            end else
            if (model[y1,x1]='W')or(damka=true) then
            begin
              if (exist(place[1,num],place[2,num],xm div width,ym div width,bx,by,black,model)=1)or
                 ((exist(place[1,num],place[2,num],xm div width,ym div width,bx,by,black,model)=0)
                   and(num=0)and(abs(place[2,num]-ym div width)>=2))or
                  (abs(place[2,num]-ym div width)=1) then
                 begin
                   permission:=true;
                   goto next;
                 end;
              end;
          next:
          if permission=true then
          begin
            x2:=xm div width;
            y2:=ym div width;
            ok:=true;
          end;
        end;
      end;
      if (l=true)and(xm div width in [1..x0])and(ym div width in [1..y0])and
         (model[ym div width,xm div width] in whites) then
      begin
        cancel;
        xm0:=xm;
        ym0:=ym;
        if (xm div width<>x1)or(ym div width<>y1) then
        begin
          x1:=xm div width;
          y1:=ym div width;
          setcolor(cursor);
          mouseoff;
          rectangle(x1*width,y1*width,(x1+1)*width,(y1+1)*width);
          mouseon;
          goto draught;
        end;
        x1:=0;
        y1:=0;
        goto restart;
      end;
    until (l=true)and(ok=true);
    xm0:=xm;
    ym0:=ym;
    num:=num+1;
    place[1,num]:=x2;
    place[2,num]:=y2;
    num0:=num;
    player(x1,y1,x2,y2,damka);
    if (mustbeat=true)and(remind=false) then
    begin
      cancel;
      confiscate(false);
    end;
    setlinestyle(solidln,0,1);
    showtime;
    delay(round((random(500)+100)*pause));
    showtime;
    computer;
    autosave;
    setlinestyle(solidln,0,1);
    inc(situation);
    if situation=1 then
    begin
      button(530,70,getmaxx-10,100,'Сохранить',true);
      button(530,10,getmaxx-10,40,'Отмена хода',true);
    end;
    opportunity:=false;
    b:=0;
    w:=0;
    for yc:=1 to y0 do
    for xc:=1 to x0 do
    begin
      if model[yc,xc] in whites then w:=w+1 else
      if model[yc,xc] in blacks then b:=b+1;
    end;
    if (b=0)or(w=0) then
    begin
      if b>0 then b:=1;
      if onceagain(b xor 1)=true then
      begin
        stroka:=stroka0;
        beat_w:=0;
        beat_b:=0;
        startgame:=false;
        mouseoff;
        board(true);
        mouseon;
        eraseall;
        goto new;
      end else quit;
    end else
    if endofgame=true then quit else
    if (hod=false)and(endofgame=false) then
    begin
      stroka:=stroka0;
      beat_w:=0;
      beat_b:=0;
      startgame:=false;
      mouseoff;
      board(true);
      mouseon;
      eraseall;
      goto new;
    end;
  until false;
end.