#!/usr/bin/perl
# Colours stdin (opencode run output) line by line to stdout and appends an ANSI-free copy to the log.
# While output is quiet it shows an animated "working" line on stderr (terminal only).
# Colour only when stdout is a terminal and NO_COLOR is unset. Works on bytes (UTF-8 passes through).
use strict; use warnings; use IO::Select; use IO::Handle; use Time::HiRes qw(time);

my $log = shift or die "usage: livelog.pl <log>\n";
open(my $L, '>>', $log) or die "$log: $!\n";
$L->autoflush(1); STDOUT->autoflush(1); STDERR->autoflush(1);

my $color = (-t STDOUT) && !$ENV{NO_COLOR};
my $tty   = -t STDERR;
my @spin  = ("\xe2\xa0\x8b","\xe2\xa0\x99","\xe2\xa0\xb9","\xe2\xa0\xb8","\xe2\xa0\xbc","\xe2\xa0\xb4","\xe2\xa0\xa6","\xe2\xa0\xa7","\xe2\xa0\x87","\xe2\xa0\x8f");
my $sel   = IO::Select->new(\*STDIN);
my ($start, $last, $status, $pend, $shown, $tick) = (time, time, 0, '', 0, 0);

sub strip { my $s = shift; $s =~ s/\e\[[0-9;?]*[A-Za-z]//g; $s =~ s/\r//g; $s }
sub dur   { my $s = int(shift); $s >= 60 ? sprintf("%dm%02ds", $s / 60, $s % 60) : "${s}s" }
sub c     { my ($code, $t) = @_; $color ? "\e[${code}m$t\e[0m" : $t }

sub paint {
  my $raw = shift; my $t = strip($raw); chomp $t;
  return "$t\n" unless $color;
  return "\n" . c('1;35', "\xe2\x96\x8d $1") . c('2', " \xc2\xb7 $2") . "\n" if $t =~ /^> (\S+) \xc2\xb7 (.+)$/;   # > build · model
  return c('2;3', $t) . "\n"                    if $t =~ /^Thinking: /;
  return c('1;36', "\$ ") . c('36', $1) . "\n"  if $t =~ /^\$ (.*)$/;                       # shell command
  return c('1;31', $t) . "\n"                   if $t =~ /^(Error|\xe2\x9c\x97)/;            # Error / ✗
  return c('1;32', "\xe2\x9c\x94 task complete") . "\n" if $t =~ /^\s*CYBER_DONE\s*$/;
  return c('33', $t) . "\n"                     if $t =~ /^(\xe2\x97\x88|%|\xe2\x86\x92|\xe2\x9c\xb1|\xe2\x9a\x99|\*) \S/;  # tool lines
  return "$t\n";
}

sub clear_status { if ($status) { print STDERR "\r\e[2K"; $status = 0 } }

while (1) {
  if ($sel->can_read(0.12)) {
    my $n = sysread(STDIN, my $buf, 65536);
    last unless $n;
    clear_status();
    $pend .= $buf;
    while ((my $i = index($pend, "\n")) >= 0) {
      my $line = substr($pend, 0, $i + 1, '');
      print $L strip($line);
      if ($shown) { print STDOUT strip(substr($line, $shown)); $shown = 0 }   # rest of a line already partly shown
      else        { print STDOUT paint($line) }
    }
    $last = time;
  } else {
    my $idle = time - $last;
    if (length($pend) > $shown && $idle > 0.4) {      # do not hold back text that has no newline yet
      clear_status();
      print STDOUT strip(substr($pend, $shown)); $shown = length $pend;
    }
    if ($tty && !$shown && $idle >= 2) {
      my $f = $spin[$tick++ % @spin];
      printf STDERR "\r\e[2K\e[36m%s\e[0m \e[2mworking %s \xc2\xb7 total %s \xc2\xb7 Ctrl-C stops\e[0m", $f, dur($idle), dur(time - $start);
      $status = 1;
    }
  }
}
clear_status();
if (length $pend) { print $L strip($pend), "\n"; print STDOUT strip(substr($pend, $shown)), "\n" }
