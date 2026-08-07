import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Flip } from "gsap/Flip";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, Flip, DrawSVGPlugin, MotionPathPlugin, useGSAP);

export { gsap, ScrollTrigger, Flip, DrawSVGPlugin, MotionPathPlugin, useGSAP };
